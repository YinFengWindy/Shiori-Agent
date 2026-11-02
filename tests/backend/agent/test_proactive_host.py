"""``PROACTIVE_HOST``: pinning, role ticks, and the host facts a tick reads."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, contextmanager, nullcontext
from datetime import datetime, timezone
from functools import partial
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

from pathlib import Path

import pytest

from agent.config_models import Config
from agent.core.turn_events import core_kernel
from agent.initiated_delivery import HostConversation, orchestrator_for
from agent.looping.ports import SessionServices
from agent.proactive_host import HostProactiveRunner
from agent.provider import LLMProvider, LLMResponse, ToolCall
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.turns.channel_sequence import ChannelSequenceOwner
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import DeliveryReceipt
from bus.event_bus import EventBus
from bus.events_lifecycle import InitiatedMessageCommitted
from bus.processing import ProcessingState
from bus.queue import MessageBus
from conversation.service import ConversationService, LegacySessionDescriptor
from core.common.runtime_scope import bind_runtime
from core.desktop_presence import DesktopPresence
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from core.roles import RoleRepository, RoleRuntimeRegistry, RoleStore
from core.roles.affection_access import AffectionGetter
from core.roles.errors import RoleNotFoundError
from core.roles.plugin_capability import HostRoles
from core.roles.reply_policy import ReplyPolicyGetter
from core.roles.reply_state import InvalidRoleReply
from core.roles.services import RoleSessionService
from plugins.natural_chat.backend.plugin import NaturalChatPolicy
from plugins.proactive.backend.state import ProactiveStateStore
from session.manager import SessionManager
from session.manager.helpers import role_session_key
from shiori_sdk.core.affection import Affection
from shiori_sdk.core.conversation import InitiatedReply, RoleReplyState
from shiori_sdk.core.proactive_host import ProactiveToolCall
from shiori_sdk.tools import Tool
from tests.support.generation_getters import turn_getters
from tests.support.proactive_runtime import (
    ProactiveGeneration,
    ProactiveRuntime,
    plugin_role_loops,
)


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


class _UnusedConversation:
    """A ``CONVERSATION`` the code under test must not touch."""

    def reply_state(self, role_id: str) -> RoleReplyState:
        raise AssertionError(role_id)

    async def deliver_initiated_reply(self, reply: InitiatedReply) -> object:
        raise AssertionError(reply)


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
    affection = AffectionGetter()
    affection.bind(lambda: None)
    policy = ReplyPolicyGetter()
    policy.bind(lambda: None)

    def unused(_role_id: str) -> TurnOrchestrator:
        raise AssertionError("reply_state does not deliver")

    conversation = HostConversation(
        unused,
        role_store=roles,
        session_manager=sessions,
        affection=affection,
        reply_policy=policy,
    )
    role = roles.get_role("mira")
    assert role is not None
    opened = RoleSessionService(sessions).open_by_role(role)
    opened.metadata["current_mood_updated_at"] = "2026-01-02T03:04:05+00:00"
    sessions.save(opened)
    runner = _runner(
        SimpleNamespace(
            conversation=conversation,
            session_manager=sessions,
            role_runtime_registry=SimpleNamespace(
                repository=SimpleNamespace(store=roles)
            ),
        )
    )
    reply = runner.validate_reply("mira", content="在", mood="想你", thought="我想你")
    assert reply.mood == "想你"
    state = conversation.reply_state("mira")
    assert state.moods == ("想你",)
    assert state.mood_updated_at == "2026-01-02T03:04:05+00:00"
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
    roles.write_plugin_proactive("mira", {"enabled": True})
    repository = RoleRepository(roles)
    old_models = _ChatModels()
    new_models = _ChatModels()
    old_registry = RoleRuntimeRegistry(repository, model_resolver=old_models)
    new_registry = RoleRuntimeRegistry(repository, model_resolver=new_models)
    old_state = ProcessingState()
    new_state = ProcessingState()
    new_state.enter(role_session_key("mira"))
    sessions = SessionManager(tmp_path)
    old_core = SimpleNamespace(
        role_runtime_registry=old_registry,
        loop=SimpleNamespace(processing_state=old_state),
    )
    new_core = SimpleNamespace(
        role_runtime_registry=new_registry,
        loop=SimpleNamespace(processing_state=new_state),
        config=Config(provider="test", model="m", api_key=""),
    )
    runner = _runner(new_core)
    old_lease = SimpleNamespace(core=old_core)
    busy: bool | None = None
    try:
        async with plugin_role_loops(
            tmp_path,
            roles=roles,
            sessions=sessions,
            proactive_host=runner,
            conversation=_UnusedConversation(),
        ) as loops:

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
    assert busy is False
    assert old_models.purposes == ["chat"]
    assert new_models.purposes == []


class _Recorder(Tool):
    """A registered host tool that records the arguments it ran with."""

    def __init__(
        self, name: str, keys: frozenset[str], seen: dict[str, dict[str, object]]
    ) -> None:
        self._name = name
        self._seen = seen
        self.context_precedence = keys

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._name

    @property
    def parameters(self) -> dict[str, object]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: object) -> str:
        self._seen[self._name] = kwargs
        return "ok"


def _tool_runner(seen: dict[str, dict[str, object]]) -> HostProactiveRunner:
    registry = ToolRegistry()
    registry.register(
        _Recorder("recall_memory", frozenset({"role_id", "session_key"}), seen)
    )
    registry.register(_Recorder("mcp_weather", frozenset(), seen))
    registry.register(_Recorder("shell", frozenset(), seen))
    return _runner(
        SimpleNamespace(
            tools=registry, plugin_manager=SimpleNamespace(kernel=core_kernel())
        )
    )


async def test_host_tools_get_only_the_role_identity_they_declare() -> None:
    """A memory tool searches the role; an MCP tool receives no identity."""
    seen: dict[str, dict[str, object]] = {}
    runner = _tool_runner(seen)

    async def host_tool(name: str, arguments: Mapping[str, object]) -> object:
        return await runner.run_host_tool(name, dict(arguments), role_id="mira")

    for name, arguments in (
        ("recall_memory", {"query": "猫", "role_id": "other"}),
        ("mcp_weather", {"city": "上海"}),
    ):
        await runner.execute_tool(
            ProactiveToolCall(call_id=name, name=name, arguments=arguments), host_tool
        )

    assert seen["recall_memory"] == {"query": "猫", "role_id": "mira"}
    assert seen["mcp_weather"] == {"city": "上海"}


async def test_host_tool_never_runs_outside_a_checked_call() -> None:
    """A plugin cannot reach shell by calling the port directly, or by
    running another tool than the one the kernel just allowed."""
    seen: dict[str, dict[str, object]] = {}
    runner = _tool_runner(seen)
    with pytest.raises(PermissionError):
        await runner.run_host_tool("shell", {"command": "rm -rf /"}, role_id="mira")

    async def smuggle(_name: str, _arguments: object) -> object:
        return await runner.run_host_tool(
            "shell", {"command": "rm -rf /"}, role_id="mira"
        )

    outcome = await runner.execute_tool(
        ProactiveToolCall(call_id="c1", name="mcp_weather", arguments={}), smuggle
    )
    assert outcome.status == "error"
    assert "shell" not in seen


def _drift_runner(workspace: Path) -> HostProactiveRunner:
    return _runner(
        SimpleNamespace(
            session_manager=SimpleNamespace(workspace=workspace),
            plugin_manager=SimpleNamespace(kernel=core_kernel()),
        )
    )


async def test_drift_writes_stay_inside_the_roles_drift_directory(
    tmp_path: Path,
) -> None:
    runner = _drift_runner(tmp_path)
    outside = tmp_path / "escape.txt"

    async def drift_file(name: str, arguments: Mapping[str, object]) -> object:
        return await runner.run_drift_file_tool("mira", name, arguments)

    for name, arguments in (
        ("write_file", {"path": "../../../escape.txt", "content": "x"}),
        ("write_file", {"path": str(outside), "content": "x"}),
        ("edit_file", {"path": str(outside), "old_text": "a", "new_text": "b"}),
        ("write_file", {"path": "notes.md", "content": "ok"}),
    ):
        await runner.execute_tool(
            ProactiveToolCall(call_id=name, name=name, arguments=arguments),
            drift_file,
        )

    assert not outside.exists()
    notes = tmp_path / "roles" / "mira" / "drift" / "notes.md"
    assert notes.read_text(encoding="utf-8") == "ok"


async def test_drift_file_tool_never_runs_outside_a_checked_call(
    tmp_path: Path,
) -> None:
    runner = _drift_runner(tmp_path)
    target = tmp_path / "roles" / "mira" / "drift" / "direct.md"
    with pytest.raises(PermissionError):
        await runner.run_drift_file_tool(
            "mira", "write_file", {"path": "direct.md", "content": "x"}
        )
    assert not target.exists()


async def test_a_loop_started_inside_a_request_does_not_keep_its_lease(
    tmp_path: Path,
) -> None:
    """A role created by a bridge request starts a loop that pins nothing."""
    from bootstrap.runtime.events import RuntimeEventBus
    from core.common.runtime_scope import current_runtime_lease
    from plugins.proactive.backend.service import ProactiveBinding, ProactiveService
    from shiori_sdk.role_events import RoleCreated
    from shiori_sdk.testing.processes import FakeProcesses

    leases: list[object] = []

    class _Loop:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self._stop = asyncio.Event()

        def stop(self) -> None:
            self._stop.set()

        async def run(self) -> None:
            leases.append(current_runtime_lease())
            await self._stop.wait()

    class _RequestLease:
        def retain(self) -> "_RequestLease":
            return self

        async def release(self) -> None:
            return None

    roles = RoleStore(tmp_path)
    service = ProactiveService(loop_factory=_Loop)
    service.attach(
        ProactiveBinding(
            host=cast(Any, SimpleNamespace(configured_max_tokens=lambda: 1)),
            conversation=cast(Any, _UnusedConversation()),
            roles=HostRoles(roles),
            processes=FakeProcesses(),
            workspace=tmp_path,
            presence=None,
            markdown=cast(Any, None),
            memory_engine=None,
            scene_followup=False,
            relationship=False,
            affection=None,
            draft_prompt=lambda: None,
            is_active=lambda: True,
        )
    )
    service.published()
    bus = RuntimeEventBus(EventBus())
    bus.on(RoleCreated, lambda _event: service.on_roles_changed())
    try:
        roles.create_role(role_id="mira", name="米拉", system_prompt="规矩")
        with bind_runtime(cast(Any, _RequestLease())):
            bus.enqueue(RoleCreated("mira"))
        await bus.drain()
        await asyncio.sleep(0)
        assert leases == [None]
    finally:
        await service.close()
        await bus.aclose()


# ── Two roles on the production assembly ─────────────────────────────────

_MOODS = {"mira": "平静", "nana": "开心"}


class _LonelyAffection:
    def render_prompt(self, role_id: str) -> str | None:
        return None

    def should_trigger_proactive(self, session_key: str, now: datetime):
        return True, {"reason": "test"}

    def handle_initiated_sent(self, session_key: str) -> None:
        return None


class _RoleScriptedProvider(LLMProvider):
    """Answers each role's requests from that role's script.

    The role is the one whose prompt opens the request. With ``together``
    each role's first request waits until every scripted role is asking.
    """

    def __init__(
        self, scripts: dict[str, list[LLMResponse]], *, together: bool
    ) -> None:
        super().__init__(
            api_key="test", model_context_window=128000, default_max_tokens=512
        )
        self.scripts = scripts
        self.asked: set[str] = set()
        self.together = asyncio.Event()
        if not together:
            self.together.set()

    async def chat(self, **kwargs: object) -> LLMResponse:  # type: ignore[override]
        messages = cast(list[dict[str, object]], kwargs["messages"])
        prompt = str(messages[0]["content"])
        role = next(role for role in self.scripts if f"ROLE-{role}" in prompt)
        if role not in self.asked:
            self.asked.add(role)
            if len(self.asked) == len(self.scripts):
                self.together.set()
            await self.together.wait()
        return self.scripts[role].pop(0)


def _tool_call(name: str, arguments: dict[str, object], raw: str | None = None):
    return LLMResponse(content="", tool_calls=[ToolCall(name, name, arguments, raw)])


def _natural_draft(role: str, messages: list[str]) -> LLMResponse:
    return _tool_call(
        "message_push",
        {"messages": messages, "mood": _MOODS[role], "thought": "我想和你说说话。"},
        json.dumps({"messages": messages}, ensure_ascii=False),
    )


@asynccontextmanager
async def _assembly(
    tmp_path,
    monkeypatch,
    scripts: dict[str, list[LLMResponse]],
    *,
    together: bool = False,
):
    """Roles with natural chat on, ticked by the production proactive assembly.

    The model, the desktop sender and affection are fakes; roles, sessions,
    the conversation and the proactive port are real.
    """
    roles = RoleStore(tmp_path)
    sessions = SessionManager(tmp_path)
    for role in scripts:
        config = {"natural_chat_enabled": True, "mood_catalog": [_MOODS[role]]}
        roles.create_role(
            role_id=role, name=role, system_prompt=f"ROLE-{role}", runtime_config=config
        )
        roles.write_plugin_proactive(role, {"enabled": True})
        sessions.save(
            sessions.open_role_session(role, role_name=role, role_runtime_config=config)
        )
    sent: list[tuple[str, str]] = []

    async def desktop_send(chat_id: str, text: str, _metadata: object) -> str:
        sent.append((chat_id, text))
        return f"desktop-{len(sent)}"

    push = MessagePushTool(role_target_validator=lambda *_args: True)
    push.register_channel("desktop", text_with_metadata=desktop_send)
    bus = EventBus()
    events: list[InitiatedMessageCommitted] = []
    bus.on(InitiatedMessageCommitted, events.append)
    tools = ToolRegistry()
    affection = AffectionGetter()
    affection.bind(lambda: cast(Affection, _LonelyAffection()))
    policy = ReplyPolicyGetter()
    policy.bind(lambda: NaturalChatPolicy())
    conversation = HostConversation(
        partial(
            orchestrator_for,
            session_manager=sessions,
            presence=sessions.presence,
            push_tool=push,
            event_bus=bus,
            tools=tools,
            role_store=roles,
        ),
        role_store=roles,
        session_manager=sessions,
        affection=affection,
        reply_policy=policy,
    )
    registry = RoleRuntimeRegistry(
        RoleRepository(roles), model_resolver=_LeaveProviderAlone()
    )
    provider = _RoleScriptedProvider(scripts, together=together)
    generation = ProactiveGeneration(
        role_runtime_registry=registry,
        loop=SimpleNamespace(processing_state=ProcessingState(), bus=MessageBus()),
        group_environment=GroupEnvironment(tmp_path, sessions.conversation_store),
        config=Config(provider="test", model="m", api_key=""),
        provider=provider,
        additional_providers=[],
        session_manager=sessions,
        tools=tools,
        plugin_manager=SimpleNamespace(kernel=core_kernel()),
        conversation=conversation,
    )
    runtime = ProactiveRuntime(generation, reply_sequences=ChannelSequenceOwner())
    runner = HostProactiveRunner(lambda: runtime)

    async def no_pause(_: object) -> None:
        return None

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", no_pause)
    try:
        async with plugin_role_loops(
            tmp_path,
            roles=roles,
            sessions=sessions,
            proactive_host=runner,
            conversation=conversation,
            affection=_LonelyAffection(),
        ) as loops:
            with turn_getters(affection=_LonelyAffection(), policy=NaturalChatPolicy()):
                yield SimpleNamespace(
                    runner=runner,
                    runtime=runtime,
                    loops=loops,
                    sent=sent,
                    events=events,
                    workspace=tmp_path,
                )
    finally:
        await registry.close_all()
        await bus.aclose()


class _LeaveProviderAlone:
    """A role model resolver that keeps the generation's provider."""

    def activate(self, role_id: str, purpose: str):
        return nullcontext(SimpleNamespace(model="role-model"))


def _assistant_rows(workspace, role: str) -> list[dict[str, Any]]:
    session = SessionManager(workspace).get_or_create(role_session_key(role))
    return [m for m in session.messages if m["role"] == "assistant"]


async def test_two_roles_ticking_together_keep_their_own_reply_and_work(
    tmp_path, monkeypatch
) -> None:
    """Both roles' ticks are open on the one process-wide port at once.

    Each role's messages, tool work and mood land on its own session and its
    own desktop chat; nothing of one role reaches the other.
    """
    scripts = {
        role: [
            _tool_call("get_recent_chat", {}),
            _natural_draft(role, [f"{role}-一", f"{role}-二"]),
            _tool_call("finish_turn", {"decision": "reply"}),
        ]
        for role in ("mira", "nana")
    }
    async with _assembly(tmp_path, monkeypatch, scripts, together=True) as env:
        await asyncio.gather(
            env.loops["mira"]._run_tick(),  # pyright: ignore[reportPrivateUsage]
            env.loops["nana"]._run_tick(),  # pyright: ignore[reportPrivateUsage]
        )

        for role in ("mira", "nana"):
            assert [text for chat, text in env.sent if chat == f"role:{role}"] == [
                f"{role}-一",
                f"{role}-二",
            ]
            rows = _assistant_rows(env.workspace, role)
            [facts] = [row for row in rows if row.get("tool_chain")]
            assert [
                call["name"] for step in facts["tool_chain"] for call in step["calls"]
            ] == ["get_recent_chat"]
            assert [row["content"] for row in rows if row["content"]] == [
                f"{role}-一",
                f"{role}-二",
            ]
            session = SessionManager(env.workspace).get_or_create(f"role:{role}")
            assert session.metadata["current_mood"] == _MOODS[role]
        assert sorted((e.role_id, e.session_key) for e in env.events) == [
            ("mira", "role:mira"),
            ("nana", "role:nana"),
        ]


async def test_delivery_inside_a_plan_refuses_another_session_or_chat(
    tmp_path, monkeypatch
) -> None:
    """A reply for another role, or another chat, cannot ride on the open plan.

    The plan has already accepted the matching draft, so only the address
    stops it.
    """
    scripts = {"mira": [_natural_draft("mira", ["借道"])], "nana": []}
    async with _assembly(tmp_path, monkeypatch, scripts) as env:
        runner = env.runner

        def reply(session_key: str, chat_id: str) -> InitiatedReply:
            return InitiatedReply(
                session_key=session_key,
                content="借道",
                source="proactive",
                channel="desktop",
                chat_id=chat_id,
                mood="平静",
                thought="我想说话。",
                expected_mood_updated_at="",
                moods=("平静",),
            )

        with ChannelSequenceOwner().bind(MessageBus()):
            async with runner.natural_reply_scope(
                runner.begin_natural_reply(),
                "role:mira",
                "desktop",
                "role:mira",
                turn_id="proactive:test",
            ):
                await runner.complete(
                    [{"role": "system", "content": "ROLE-mira"}], natural_draft=True
                )
                assert runner.natural_reply_messages() == ("借道",)
                with pytest.raises(ValueError):
                    await runner.deliver(reply("role:nana", "role:nana"))
                with pytest.raises(ValueError):
                    await runner.deliver(reply("role:mira", "role:nana"))

        assert env.sent == []
        assert _assistant_rows(env.workspace, "mira") == []
        assert _assistant_rows(env.workspace, "nana") == []


async def test_failed_mood_write_after_a_full_sequence_still_counts_as_sent(
    tmp_path, monkeypatch
) -> None:
    """Every message went out and was stored; only the final mood write failed.

    The delivery is recorded, so the same message is not sent again later.
    """

    async def fail(*_args: object) -> None:
        raise RuntimeError("心情写入失败")

    monkeypatch.setattr("agent.turns.proactive_sequence.publish_final_role_state", fail)
    scripts = {
        "mira": [
            _natural_draft("mira", ["在吗？", "想你了。"]),
            _tool_call("finish_turn", {"decision": "reply"}),
        ]
    }
    async with _assembly(tmp_path, monkeypatch, scripts) as env:
        await env.loops["mira"]._run_tick()  # pyright: ignore[reportPrivateUsage]

        assert [text for _chat, text in env.sent] == ["在吗？", "想你了。"]
        store = ProactiveStateStore(env.workspace / "roles" / "mira" / "proactive.db")
        assert store.count_deliveries_in_window("role:mira", 24) == 1
