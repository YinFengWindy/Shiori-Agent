from __future__ import annotations

import asyncio
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.roles.services import RoleRepository
from core.roles.store import RoleStore
from core.roles.role_runtime import RoleExecutionContext, RoleRuntimeRegistry
from agent.config_models import ModelRegistration
from core.roles.model_errors import ModelConfigurationError
from core.roles.model_runtime import RoleModelRuntime
from core.roles.self_initializer import RoleSelfInitializer
from core.roles.self_seed import LlmRoleSelfSeedGenerator
from bus.event_bus import EventBus
from bus.events_context import ContextWindowChanged


@pytest.mark.parametrize("fails", [False, True])
async def test_context_refresh_is_published_after_role_gate_release(tmp_path, fails):
    store = RoleStore(tmp_path)
    role = store.create_role(role_id="mira", name="Mira", system_prompt="test")
    bus = EventBus()
    registry = RoleRuntimeRegistry(RoleRepository(store), event_bus=bus)
    runtime = await registry.get(role.id)
    observed = []
    bus.on(
        ContextWindowChanged,
        lambda event: observed.append((event.session_key, runtime.busy)),
    )

    async def operation():
        assert runtime.busy
        if fails:
            raise RuntimeError("failed formal turn")

    if fails:
        with pytest.raises(RuntimeError, match="failed formal turn"):
            await runtime.execute_thread(_context(role), operation)
    else:
        await runtime.execute_thread(_context(role), operation)
    assert observed == [("role:mira", False)]


def _context(role, *, thread_id: str = "thread:mira:desktop"):
    return RoleExecutionContext.create(
        role=role,
        thread_id=thread_id,
        transport_channel="desktop",
        transport_chat_id="self",
        source="test",
        work_kind="passive_turn",
        request_id="request-1",
        delivery_key="delivery-1",
    )


@pytest.mark.asyncio
async def test_first_turn_seeds_once_across_channels_and_runtime_generations(
    tmp_path, monkeypatch
):
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
        runtime_config={
            "dialogue_model_registration_id": "dialogue",
            "visual_model_registration_id": "visual",
        },
    )
    registrations = [
        ModelRegistration(
            context_window_tokens=128000,
            max_output_tokens=32768,
            id=key,
            provider="openai",
            model=key,
            api_key="fake",
            base_url="",
        )
        for key in ("dialogue", "visual")
    ]
    provider = SimpleNamespace(chat=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(
        "core.roles.model_runtime.LLMProvider", lambda **kwargs: provider
    )
    models = RoleModelRuntime(role_store=store, registrations=registrations)
    repository = RoleRepository(store)
    registry = RoleRuntimeRegistry(
        repository,
        model_resolver=models,
        self_initializer=RoleSelfInitializer(store, LlmRoleSelfSeedGenerator()),
    )
    reloaded = RoleRuntimeRegistry(
        repository,
        model_resolver=models,
        shared_execution=registry,
        self_initializer=RoleSelfInitializer(store, LlmRoleSelfSeedGenerator()),
    )
    entered, release = asyncio.Event(), asyncio.Event()
    order = []

    async def seed(**kwargs):
        assert kwargs["model"] == "dialogue"
        order.append("seed")
        entered.set()
        await release.wait()
        return SimpleNamespace(content="# 我是谁\n\n已初始化")

    provider.chat.side_effect = seed

    async def reply():
        assert "已初始化" in (tmp_path / "roles/mira/memory/SELF.md").read_text(
            encoding="utf-8"
        )
        order.append("reply")

    # An image request may already carry a visual snapshot at the desktop boundary.
    with models.activate(role.id, "vision"):
        first = asyncio.create_task(
            registry.dispatch_passive_turn(_context(role), reply)
        )
        await asyncio.wait_for(entered.wait(), 2)
        other = RoleExecutionContext.create(
            role=role,
            thread_id="telegram:42",
            transport_channel="telegram",
            transport_chat_id="42",
            source="test",
            work_kind="passive_turn",
        )
        second = asyncio.create_task(reloaded.dispatch_passive_turn(other, reply))
        await asyncio.sleep(0)
        assert order == ["seed"]
        release.set()
        await asyncio.gather(first, second)
    assert order == ["seed", "reply", "reply"]
    provider.chat.assert_awaited_once()
    await models.aclose()


@pytest.mark.asyncio
async def test_unbound_first_turn_stops_before_seed_and_can_retry_after_binding(
    tmp_path, monkeypatch
):
    store = RoleStore(tmp_path)
    role = store.create_role(role_id="mira", name="Mira", system_prompt="test")
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="self")), aclose=AsyncMock()
    )
    monkeypatch.setattr(
        "core.roles.model_runtime.LLMProvider", lambda **kwargs: provider
    )
    models = RoleModelRuntime(
        role_store=store,
        registrations=[
            ModelRegistration(
                context_window_tokens=128000,
                max_output_tokens=32768,
                id="dialogue",
                provider="openai",
                model="selected",
                api_key="fake",
                base_url="",
            ),
        ],
    )
    registry = RoleRuntimeRegistry(
        RoleRepository(store),
        model_resolver=models,
        self_initializer=RoleSelfInitializer(store, LlmRoleSelfSeedGenerator()),
    )
    reply = AsyncMock()
    with pytest.raises(ModelConfigurationError, match="请先绑定"):
        await registry.dispatch_passive_turn(_context(role), reply)
    provider.chat.assert_not_called()
    reply.assert_not_called()
    store.update_role(
        role.id, runtime_config={"dialogue_model_registration_id": "dialogue"}
    )
    await registry.dispatch_passive_turn(_context(role), reply)
    provider.chat.assert_awaited_once()
    reply.assert_awaited_once()
    await models.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted_before_seed", [True, False])
async def test_text_reply_respects_when_its_model_snapshot_is_accepted(
    tmp_path, monkeypatch, accepted_before_seed
):
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
        runtime_config={
            "dialogue_model_registration_id": "first",
        },
    )
    provider = SimpleNamespace(chat=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(
        "core.roles.model_runtime.LLMProvider", lambda **kwargs: provider
    )
    models = RoleModelRuntime(
        role_store=store,
        registrations=[
            ModelRegistration(
                context_window_tokens=128000,
                max_output_tokens=32768,
                id=key,
                provider="openai",
                model=key,
                api_key="fake",
                base_url="",
            )
            for key in ("first", "second")
        ],
    )
    registry = RoleRuntimeRegistry(
        RoleRepository(store),
        model_resolver=models,
        self_initializer=RoleSelfInitializer(store, LlmRoleSelfSeedGenerator()),
    )

    async def seed(**kwargs):
        store.update_role(
            role.id, runtime_config={"dialogue_model_registration_id": "second"}
        )
        return SimpleNamespace(content="self")

    provider.chat.side_effect = seed

    async def reply():
        with (await registry.get(role.id)).activate_model("chat") as snapshot:
            return snapshot.model

    scope = models.activate(role.id, "chat") if accepted_before_seed else nullcontext()
    with scope:
        assert await registry.dispatch_passive_turn(_context(role), reply) == (
            "first" if accepted_before_seed else "second"
        )
    assert await registry.dispatch_passive_turn(_context(role), reply) == "second"
    provider.chat.assert_awaited_once()
    await models.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("already_seeded", [False, True])
@pytest.mark.parametrize("next_visual", ["new-vision", "missing-registration"])
async def test_image_reply_preserves_accepted_snapshot_after_initialization(
    tmp_path,
    monkeypatch,
    already_seeded,
    next_visual,
):
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
        runtime_config={
            "dialogue_model_registration_id": "dialogue",
            "visual_model_registration_id": "old-vision",
        },
    )
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="self")), aclose=AsyncMock()
    )
    monkeypatch.setattr(
        "core.roles.model_runtime.LLMProvider", lambda **kwargs: provider
    )
    models = RoleModelRuntime(
        role_store=store,
        registrations=[
            ModelRegistration(
                context_window_tokens=128000,
                max_output_tokens=32768,
                id=key,
                provider="openai",
                model=key,
                api_key="fake",
                base_url="",
            )
            for key in ("dialogue", "old-vision", "new-vision")
        ],
    )
    initializer = RoleSelfInitializer(store, LlmRoleSelfSeedGenerator())
    registry = RoleRuntimeRegistry(
        RoleRepository(store), model_resolver=models, self_initializer=initializer
    )
    if already_seeded:
        await initializer.ensure_seeded(role.id, models.resolve(role.id, "chat"))

    async def reply():
        assert (
            store.get_role(role.id).memory_init_state["self_seed"]["status"]
            == "generated"
        )
        with (await registry.get(role.id)).activate_model("vision") as snapshot:
            return snapshot

    try:
        with models.activate(role.id, "vision") as accepted:
            # The request was accepted before a settings change while waiting for its turn.
            store.update_role(
                role.id,
                runtime_config={
                    "dialogue_model_registration_id": "dialogue",
                    "visual_model_registration_id": next_visual,
                },
            )
            assert (
                await registry.dispatch_passive_turn(_context(role), reply) is accepted
            )
        provider.chat.assert_awaited_once()
        assert provider.chat.await_args.kwargs["model"] == "dialogue"
    finally:
        await models.aclose()


@pytest.mark.asyncio
async def test_generations_share_role_execution_gate(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    original = RoleRuntimeRegistry(repository)
    updated = RoleRuntimeRegistry(repository, shared_execution=original)
    entered = asyncio.Event()
    release = asyncio.Event()
    events = []

    async def first():
        entered.set()
        await release.wait()
        events.append("old")

    async def second():
        events.append("new")

    old_task = asyncio.create_task(original.dispatch_thread(_context(role), first))
    await entered.wait()
    new_task = asyncio.create_task(updated.dispatch_thread(_context(role), second))
    await asyncio.sleep(0)
    assert events == []
    assert (await updated.get(role.id)).active_work == 1
    release.set()
    await asyncio.gather(old_task, new_task)
    assert events == ["old", "new"]


@pytest.mark.asyncio
async def test_registry_serializes_work_in_the_same_thread(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
    )
    registry = RoleRuntimeRegistry(repository)
    context = _context(role)
    events: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> str:
        events.append("first:start")
        first_started.set()
        await release_first.wait()
        events.append("first:end")
        return "first"

    async def second() -> str:
        events.append("second")
        return "second"

    first_task = asyncio.create_task(registry.dispatch_thread(context, first))
    await first_started.wait()
    second_task = asyncio.create_task(registry.dispatch_thread(context, second))
    await asyncio.sleep(0)
    assert events == ["first:start"]

    release_first.set()
    assert await first_task == "first"
    assert await second_task == "second"
    assert events == ["first:start", "first:end", "second"]


@pytest.mark.asyncio
async def test_registry_serializes_different_transport_threads_for_one_role(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    registry = RoleRuntimeRegistry(repository)
    events: list[str] = []
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> str:
        events.append("first:start")
        first_started.set()
        await release_first.wait()
        events.append("first:end")
        return "first"

    async def second() -> str:
        events.append("second")
        return "second"

    first_task = asyncio.create_task(
        registry.dispatch_thread(
            _context(role, thread_id="thread:mira:telegram:1"),
            first,
        )
    )
    await first_started.wait()
    second_task = asyncio.create_task(
        registry.dispatch_thread(
            _context(role, thread_id="thread:mira:qq:2"),
            second,
        )
    )
    await asyncio.sleep(0)
    assert events == ["first:start"]

    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert events == ["first:start", "first:end", "second"]


@pytest.mark.asyncio
async def test_registry_allows_different_roles_to_execute_independently(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    mira = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    shiori = repository.create_role(
        role_id="shiori",
        name="Shiori",
        system_prompt="test",
    )
    registry = RoleRuntimeRegistry(repository)
    mira_started = asyncio.Event()
    shiori_started = asyncio.Event()
    release = asyncio.Event()

    async def wait_for(started: asyncio.Event) -> None:
        started.set()
        await release.wait()

    mira_task = asyncio.create_task(
        registry.dispatch_thread(_context(mira), lambda: wait_for(mira_started))
    )
    shiori_task = asyncio.create_task(
        registry.dispatch_thread(_context(shiori), lambda: wait_for(shiori_started))
    )
    await asyncio.wait_for(
        asyncio.gather(mira_started.wait(), shiori_started.wait()), 0.2
    )
    release.set()
    await asyncio.gather(mira_task, shiori_task)


@pytest.mark.asyncio
async def test_role_runtime_owns_role_model_activation(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    activations: list[tuple[str, str]] = []

    class _ModelRuntime:
        @contextmanager
        def activate(self, role_id: str, purpose: str):
            activations.append((role_id, purpose))
            yield SimpleNamespace(model="role-model")

    registry = RoleRuntimeRegistry(repository, model_resolver=_ModelRuntime())
    runtime = await registry.get(role.id)

    with runtime.activate_model("vision") as snapshot:
        assert snapshot.model == "role-model"

    assert activations == [("mira", "vision")]


@pytest.mark.asyncio
async def test_role_runtime_rejects_model_activation_when_capability_is_missing(
    tmp_path,
):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    runtime = await RoleRuntimeRegistry(repository).get(role.id)

    with pytest.raises(RuntimeError, match="未配置模型能力"):
        with runtime.activate_model("chat"):
            pass


@pytest.mark.asyncio
async def test_role_capabilities_reject_the_wrong_work_kind(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(role_id="mira", name="Mira", system_prompt="test")
    registry = RoleRuntimeRegistry(repository)

    with pytest.raises(ValueError, match="不接受工作类型"):
        await registry.dispatch_proactive_tick(_context(role), _return_none)


@pytest.mark.asyncio
async def test_registry_refreshes_configuration_without_replacing_the_runtime(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
    )
    registry = RoleRuntimeRegistry(repository)
    context = _context(role)
    first_runtime = await registry.get(role.id)
    updated = repository.update_role(role.id, description="updated")
    refreshed_runtime = await registry.get(role.id)

    assert refreshed_runtime is first_runtime
    assert refreshed_runtime.config_version != context.role_config_version
    await registry.dispatch_thread(context, lambda: _return_none())
    assert (
        refreshed_runtime.config_version
        == RoleExecutionContext.create(
            role=updated,
            thread_id=context.thread_id,
            transport_channel=context.transport_channel,
            transport_chat_id=context.transport_chat_id,
            source=context.source,
            work_kind=context.work_kind,
        ).role_config_version
    )


async def _return_none() -> None:
    return None


def test_registry_builds_direct_context_from_authoritative_role(tmp_path):
    repository = RoleRepository(RoleStore(tmp_path))
    role = repository.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
    )
    registry = RoleRuntimeRegistry(repository)

    context = registry.create_context(
        role_id=role.id,
        thread_id="thread:mira:desktop",
        transport_channel="desktop",
        transport_chat_id="role:mira",
        source="desktop",
        work_kind="passive_turn",
    )

    assert context.role_id == "mira"
    assert context.thread_id == "thread:mira:desktop"
    assert context.role_config_version
