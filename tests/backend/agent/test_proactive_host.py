"""``PROACTIVE_HOST``: pinning, role ticks, and the host facts a tick reads."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from agent.config_models import Config
from agent.core.turn_events import core_kernel
from agent.initiated_delivery import HostConversation
from agent.looping.ports import SessionServices
from agent.proactive_host import HostProactiveRunner
from agent.provider import LLMProvider
from agent.tools.message_push import MessagePushTool
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import DeliveryReceipt
from bootstrap.proactive import build_proactive_runtime
from bus.event_bus import EventBus
from bus.processing import ProcessingState
from conversation.service import ConversationService, LegacySessionDescriptor
from core.common.runtime_scope import bind_runtime
from core.desktop_presence import DesktopPresence
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from core.roles import RoleRepository, RoleRuntimeRegistry, RoleStore
from core.roles.affection_access import AffectionGetter
from core.roles.errors import RoleNotFoundError
from core.roles.reply_policy import ReplyPolicyGetter
from core.roles.reply_state import InvalidRoleReply
from session.manager import SessionManager
from session.manager.helpers import role_session_key
from shiori_sdk.core.conversation import InitiatedReply
from shiori_sdk.core.proactive_host import ProactiveToolCall


class _Lease:
    def __init__(self, runtime: "_Runtime") -> None:
        self.core = runtime.core

    async def __aenter__(self) -> "_Lease":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _Runtime:
    def __init__(self, core: object) -> None:
        self.core = core
        self.desktop_presence = DesktopPresence()

    def acquire(self) -> _Lease:
        return _Lease(self)

    async def wait_for_admission(self) -> None:
        return None


def _runner(core: object) -> HostProactiveRunner:
    return HostProactiveRunner(lambda: _Runtime(core))


def _role_core(tmp_path, *, catalog: list[str] | None = None):
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="米拉",
        system_prompt="只有米拉会说的规矩",
        runtime_config={"mood_catalog": catalog} if catalog is not None else None,
    )
    return roles, SessionManager(tmp_path)


class _ChatModels:
    def __init__(self) -> None:
        self.purposes: list[str] = []

    @contextmanager
    def activate(self, role_id: str, purpose: str):
        self.purposes.append(purpose)
        yield SimpleNamespace(role_id=role_id)


async def test_ticks_on_one_role_do_not_overlap(tmp_path) -> None:
    repository = RoleRepository(RoleStore(tmp_path))
    repository.create_role(role_id="mira", name="米拉", system_prompt="规矩")
    registry = RoleRuntimeRegistry(repository, model_resolver=_ChatModels())
    runner = _runner(SimpleNamespace(role_runtime_registry=registry))
    entered = asyncio.Event()
    release = asyncio.Event()
    order: list[str] = []

    async def first() -> None:
        order.append("enter")
        entered.set()
        await release.wait()
        order.append("leave")

    async def second() -> None:
        order.append("next")

    first_task = asyncio.create_task(runner.run_tick("mira", first))
    await entered.wait()
    second_task = asyncio.create_task(runner.run_tick("mira", second))
    await asyncio.sleep(0.05)
    assert order == ["enter"]
    release.set()
    await asyncio.gather(first_task, second_task)
    assert order == ["enter", "leave", "next"]


async def test_missing_role_is_not_executed(tmp_path) -> None:
    registry = RoleRuntimeRegistry(RoleRepository(RoleStore(tmp_path)))
    runner = _runner(SimpleNamespace(role_runtime_registry=registry))
    ran = False

    async def operation() -> None:
        nonlocal ran
        ran = True

    with pytest.raises(RoleNotFoundError):
        await runner.run_tick("missing", operation)
    assert ran is False


async def test_tick_activates_the_chat_model(tmp_path) -> None:
    repository = RoleRepository(RoleStore(tmp_path))
    repository.create_role(role_id="mira", name="米拉", system_prompt="规矩")
    models = _ChatModels()
    registry = RoleRuntimeRegistry(repository, model_resolver=models)
    runner = _runner(SimpleNamespace(role_runtime_registry=registry))

    async def operation() -> str:
        return "done"

    assert await runner.run_tick("mira", operation) == "done"
    assert models.purposes == ["chat"]


def test_passive_turn_busy_follows_the_published_processing_state() -> None:
    state = ProcessingState()

    class _Impatient:
        def __init__(self) -> None:
            self.core = SimpleNamespace(loop=SimpleNamespace(processing_state=state))

        async def wait_for_admission(self) -> None:
            raise AssertionError("passive busy check waited for admission")

        def acquire(self) -> None:
            raise AssertionError("passive busy check pinned a generation")

    runtime = _Impatient()
    runner = HostProactiveRunner(lambda: runtime)
    assert runner.passive_turn_busy("mira") is False
    state.enter(role_session_key("mira"))
    assert runner.passive_turn_busy("mira") is True
    assert runner.passive_turn_busy("other") is False
    runtime.core = SimpleNamespace(
        loop=SimpleNamespace(processing_state=ProcessingState())
    )
    assert runner.passive_turn_busy("mira") is False


async def test_destructive_shell_is_denied_before_the_tool_runs() -> None:
    ran = False

    async def invoker(name: str, arguments: object) -> str:
        nonlocal ran
        ran = True
        return name

    runner = _runner(
        SimpleNamespace(plugin_manager=SimpleNamespace(kernel=core_kernel()))
    )
    outcome = await runner.execute_tool(
        ProactiveToolCall(
            call_id="call-1",
            name="shell",
            arguments={"command": "rm -rf /"},
        ),
        invoker,
    )
    assert outcome.status == "denied"
    assert ran is False


class _Generation:
    """The parts of one generation's core that ``complete`` reads."""

    def __init__(self, api_key: str) -> None:
        self.config = SimpleNamespace(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            provider="dashscope",
            extra_body={"enable_thinking": True},
            model="qwen",
            max_tokens=32,
        )
        self.provider = LLMProvider(api_key="unused")
        self.additional_providers: list[LLMProvider] = []

    async def aclose(self) -> None:
        for provider in self.additional_providers:
            await provider.aclose()


def _record_requests(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, dict]]:
    """Answer every provider request with text; record (provider, extra_body)."""
    requests: list[tuple[object, dict]] = []

    async def transport(self, kwargs, *, payload_snapshot_enabled=None):
        del payload_snapshot_enabled
        requests.append((self, dict(kwargs.get("extra_body") or {})))
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="带伞", tool_calls=None),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(LLMProvider, "_create_with_retry", transport)
    return requests


async def test_completion_forces_thinking_off_on_the_fallback_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _record_requests(monkeypatch)
    generation = _Generation("test-key")
    runner = _runner(generation)
    try:
        completion = await runner.complete(
            [{"role": "user", "content": "出门吗"}],
            disable_thinking=False,
        )
    finally:
        await generation.aclose()
    assert completion.content == "带伞"
    [(_provider, body)] = requests
    assert body.get("enable_thinking") is False


async def test_completion_provider_closes_with_its_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A config change publishes a new generation; each keeps one provider.

    An old generation's long tick and the new generation's ticks interleave
    while the old one drains; neither rebuilds its provider.
    """
    requests = _record_requests(monkeypatch)
    first, second = _Generation("first-key"), _Generation("second-key")
    runtime = _Runtime(first)
    runner = HostProactiveRunner(lambda: runtime)
    try:
        for core in (first, second, first, second, first):
            runtime.core = core
            await runner.complete([{"role": "user", "content": "早"}])
    finally:
        await first.aclose()
        await second.aclose()
    used = [provider for provider, _body in requests]
    assert first.additional_providers == [used[0]]
    assert second.additional_providers == [used[1]]
    assert used == [used[0], used[1], used[0], used[1], used[0]]


def test_desktop_presence_follows_the_process_report() -> None:
    runtime = _Runtime(SimpleNamespace())
    runner = HostProactiveRunner(lambda: runtime)
    assert runner.user_at_desktop() is True
    runtime.desktop_presence.report(False)
    assert runner.user_at_desktop() is False


def test_recent_activity_skips_the_desktop_thread(tmp_path) -> None:
    roles, sessions = _role_core(tmp_path)
    service = ConversationService(sessions)
    env = GroupEnvironment(tmp_path, sessions.conversation_store)
    desktop = service.ensure_desktop_thread("mira")
    external = service.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:cats",
            role_id="mira",
            channel="telegram",
            chat_id="cats",
        )
    )
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    env.apply(
        "mira",
        GroupEnvironmentUpdate(external.id, "猫群", "猫猫在聊", ""),
        updated_at=now,
    )
    env.apply(
        "mira",
        GroupEnvironmentUpdate(desktop.id, "桌面", "桌面不该出现", ""),
        updated_at=now,
    )
    runner = _runner(SimpleNamespace(group_environment=env))
    text = runner.recent_activity("mira", now=now)
    assert "猫猫在聊" in text
    assert "桌面不该出现" not in text


def test_role_prompt_includes_behavior_rules(tmp_path) -> None:
    roles, _sessions = _role_core(tmp_path)
    runner = _runner(
        SimpleNamespace(
            role_runtime_registry=SimpleNamespace(
                repository=SimpleNamespace(store=roles)
            )
        )
    )
    assert "只有米拉会说的规矩" in runner.compile_role_prompt("mira")


def test_reply_validation_uses_the_role_mood_catalog(tmp_path) -> None:
    roles, sessions = _role_core(tmp_path, catalog=["想你"])
    runner = _runner(
        SimpleNamespace(
            session_manager=sessions,
            role_runtime_registry=SimpleNamespace(
                repository=SimpleNamespace(store=roles)
            ),
        )
    )
    reply = runner.validate_reply("mira", content="在", mood="想你", thought="我想你")
    assert reply.mood == "想你"
    assert runner.reply_state("mira").moods == ("想你",)
    with pytest.raises(InvalidRoleReply):
        runner.validate_reply("mira", content="在", mood="平静", thought="我想你")


def _host_conversation(root, bus: EventBus) -> tuple[HostConversation, SessionManager]:
    roles = RoleStore(root)
    roles.create_role(
        role_id="mira",
        name="米拉",
        system_prompt="规矩",
        runtime_config={"mood_catalog": ["想你"]},
    )
    manager = SessionManager(root)
    affection = AffectionGetter()
    affection.bind(lambda: None)
    reply_policy = ReplyPolicyGetter()
    reply_policy.bind(lambda: None)

    def build(role_id: str) -> TurnOrchestrator:
        async def dispatch(message):
            return DeliveryReceipt.sent()

        return TurnOrchestrator(
            TurnOrchestratorDeps(
                session=SessionServices(
                    manager, conversation_service=ConversationService(manager)
                ),
                outbound=SimpleNamespace(dispatch=dispatch),
                event_bus=bus,
                role_lookup=roles.get_role,
            )
        )

    conversation = HostConversation(
        build,
        role_store=roles,
        session_manager=manager,
        affection=affection,
        reply_policy=reply_policy,
    )
    return conversation, manager


async def test_deliver_uses_the_generation_published_for_that_call(tmp_path) -> None:
    first_bus = EventBus()
    second_bus = EventBus()
    first, first_store = _host_conversation(tmp_path / "first", first_bus)
    second, second_store = _host_conversation(tmp_path / "second", second_bus)
    runtime = _Runtime(SimpleNamespace(conversation=first))
    runner = HostProactiveRunner(lambda: runtime)

    def reply(text: str) -> InitiatedReply:
        return InitiatedReply(
            session_key="role:mira",
            content=text,
            source="drift",
            channel="desktop",
            chat_id="role:mira",
            mood="想你",
            thought="我想你",
            expected_mood_updated_at="",
            moods=("想你",),
        )

    try:
        await runner.deliver(reply("第一代"))
        runtime.core = SimpleNamespace(conversation=second)
        await runner.deliver(reply("第二代"))
    finally:
        await first_bus.aclose()
        await second_bus.aclose()

    assert [
        row["content"] for row in first_store._store.fetch_session_messages("role:mira")
    ] == ["第一代"]
    assert [
        row["content"]
        for row in second_store._store.fetch_session_messages("role:mira")
    ] == ["第二代"]


async def test_held_lease_keeps_the_draining_generation(tmp_path) -> None:
    """A tick that still holds the old generation uses that generation.

    Production starts the loop inside ``bind_runtime(lease)``. Dropping the
    held lease and pinning the published generation would activate the new
    chat model and read the new generation's passive-busy flag while the
    draining tick still uses the old provider, session and tools.
    """
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="米拉", system_prompt="规矩")
    roles.update_role("mira", proactive={"enabled": True})
    repository = RoleRepository(roles)
    old_models = _ChatModels()
    new_models = _ChatModels()
    old_registry = RoleRuntimeRegistry(repository, model_resolver=old_models)
    new_registry = RoleRuntimeRegistry(repository, model_resolver=new_models)
    old_state = ProcessingState()
    new_state = ProcessingState()
    new_state.enter(role_session_key("mira"))
    sessions = SessionManager(tmp_path)
    provider = LLMProvider(api_key="test")
    old_core = SimpleNamespace(
        role_runtime_registry=old_registry,
        loop=SimpleNamespace(processing_state=old_state),
    )
    new_core = SimpleNamespace(
        role_runtime_registry=new_registry,
        loop=SimpleNamespace(processing_state=new_state),
    )
    runner = _runner(new_core)
    old_lease = SimpleNamespace(core=old_core)
    busy: bool | None = None
    try:
        tasks, loops = build_proactive_runtime(
            Config(provider="test", model="m", api_key=""),
            tmp_path,
            session_manager=sessions,
            provider=provider,
            light_provider=provider,
            push_tool=MessagePushTool(role_target_validator=lambda *_args: True),
            memory_store=None,
            presence=sessions.presence,
            agent_loop=SimpleNamespace(  # type: ignore[arg-type]
                role_runtime_registry=old_registry, tools=None
            ),
            kernel=core_kernel,
            proactive_host=runner,
            group_environment=GroupEnvironment(tmp_path, sessions.conversation_store),
        )
        for task in tasks:
            task.close()

        async def operation() -> None:
            nonlocal busy
            busy = runner.passive_turn_busy("mira")

        with bind_runtime(old_lease):  # type: ignore[arg-type]
            await loops["mira"]._tick_dispatcher(
                operation
            )  # pyright: ignore[reportPrivateUsage]
    finally:
        await old_registry.close_all()
        await new_registry.close_all()
        await provider.aclose()
    assert busy is False
    assert old_models.purposes == ["chat"]
    assert new_models.purposes == []
