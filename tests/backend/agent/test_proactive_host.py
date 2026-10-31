"""``PROACTIVE_HOST``: pinning, role ticks, and the host facts a tick reads."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from agent.core.turn_events import core_kernel
from agent.initiated_delivery import HostConversation
from agent.looping.ports import SessionServices
from agent.proactive_host import HostProactiveRunner
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import DeliveryReceipt
from agent.provider import LLMProvider
from bootstrap.plugin_core import PluginCoreInputs, plugin_core_modules
from bus.event_bus import EventBus
from bus.processing import ProcessingState
from conversation.context_scope import load_user_context_threads
from conversation.service import ConversationService, LegacySessionDescriptor
from core.desktop_presence import DesktopPresence
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from core.memory.markdown.recent_context_document import stamp_recent_context
from core.memory.markdown.runtime import MarkdownMemoryStore
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


async def test_completion_forces_thinking_off_on_the_fallback_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_body: dict[str, object] = {}

    async def transport(self, kwargs, *, payload_snapshot_enabled=None):
        del self, payload_snapshot_enabled
        seen_body.update(dict(kwargs.get("extra_body") or {}))
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
    config = SimpleNamespace(
        api_key="test-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        provider="dashscope",
        extra_body={"enable_thinking": True},
        model="qwen",
        max_tokens=32,
    )
    runner = _runner(
        SimpleNamespace(config=config, provider=LLMProvider(api_key="unused"))
    )
    try:
        completion = await runner.complete(
            [{"role": "user", "content": "出门吗"}],
            disable_thinking=False,
        )
    finally:
        await runner.aclose()
    assert completion.content == "带伞"
    assert seen_body.get("enable_thinking") is False


def test_desktop_presence_follows_the_process_report() -> None:
    runtime = _Runtime(SimpleNamespace())
    runner = HostProactiveRunner(lambda: runtime)
    assert runner.user_at_desktop() is True
    runtime.desktop_presence.report(False)
    assert runner.user_at_desktop() is False


def test_group_note_is_the_role_own_note(tmp_path) -> None:
    roles, sessions = _role_core(tmp_path)
    roles.create_role(role_id="other", name="别人", system_prompt="别的规矩")
    env = GroupEnvironment(tmp_path, sessions.conversation_store)
    thread = ConversationService(sessions).ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:cats",
            role_id="mira",
            channel="telegram",
            chat_id="cats",
        )
    )
    env.write_note("mira", thread.id, "米拉记下了猫")
    env.write_note("other", thread.id, "别人的笔记")
    runner = _runner(
        SimpleNamespace(
            group_environment=env,
            role_runtime_registry=SimpleNamespace(
                repository=SimpleNamespace(store=roles)
            ),
        )
    )
    text = runner.group_note("mira", thread.id)
    assert "米拉记下了猫" in text
    assert "别人的笔记" not in text


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


def test_affection_prompt_follows_the_bound_socket(tmp_path) -> None:
    roles, _sessions = _role_core(tmp_path)

    class _Socket:
        def __init__(self, text: str | None) -> None:
            self._text = text

        def render_prompt(self, role_id: str) -> str | None:
            del role_id
            return self._text

    getter = AffectionGetter()
    getter.bind(lambda: _Socket("阶段：朋友"))
    runner = _runner(
        SimpleNamespace(
            affection=getter,
            role_runtime_registry=SimpleNamespace(
                repository=SimpleNamespace(store=roles)
            ),
        )
    )
    assert runner.affection_prompt("mira") == "阶段：朋友"
    getter.bind(lambda: None)
    assert runner.affection_prompt("mira") is None


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


def test_workspace_skill_hides_the_builtin_of_the_same_name(tmp_path) -> None:
    roles, _sessions = _role_core(tmp_path)
    builtin = tmp_path / "builtin-skills" / "umbrella"
    builtin.mkdir(parents=True)
    (builtin / "SKILL.md").write_text("builtin-umbrella-body\n", encoding="utf-8")
    workspace_skill = tmp_path / "skills" / "umbrella"
    workspace_skill.mkdir(parents=True)
    (workspace_skill / "SKILL.md").write_text(
        "workspace-umbrella-body\n", encoding="utf-8"
    )
    runner = HostProactiveRunner(
        lambda: _Runtime(
            SimpleNamespace(
                role_runtime_registry=SimpleNamespace(
                    repository=SimpleNamespace(store=roles)
                )
            )
        ),
        builtin_skills_dir=tmp_path / "builtin-skills",
    )
    listed = next(item for item in runner.list_skills() if item.name == "umbrella")
    rendered = runner.render_skills(["umbrella"])
    assert listed.source == "workspace"
    assert "workspace-umbrella-body" in rendered
    assert "builtin-umbrella-body" not in rendered


def test_recent_context_returns_the_visible_body(tmp_path) -> None:
    roles, _sessions = _role_core(tmp_path)
    threads = load_user_context_threads(tmp_path, "mira")
    MarkdownMemoryStore(tmp_path / "roles" / "mira").write_recent_context(
        stamp_recent_context("刚聊过伞", threads)
    )
    runner = _runner(
        SimpleNamespace(
            role_runtime_registry=SimpleNamespace(
                repository=SimpleNamespace(store=roles)
            )
        )
    )
    text = runner.recent_context("mira")
    assert "刚聊过伞" in text
    assert "shiori-recent-context" not in text


def test_recent_context_of_a_missing_role_does_not_create_a_directory(tmp_path) -> None:
    roles, _sessions = _role_core(tmp_path)
    runner = _runner(
        SimpleNamespace(
            role_runtime_registry=SimpleNamespace(
                repository=SimpleNamespace(store=roles)
            )
        )
    )
    assert runner.recent_context("gone") == ""
    assert not (tmp_path / "roles" / "gone").exists()


def _host_conversation(manager: SessionManager, bus: EventBus) -> HostConversation:
    affection = AffectionGetter()
    affection.bind(lambda: None)
    reply_policy = ReplyPolicyGetter()
    reply_policy.bind(lambda: None)

    def build() -> TurnOrchestrator:
        async def dispatch(message):
            return DeliveryReceipt.sent()

        return TurnOrchestrator(
            TurnOrchestratorDeps(
                session=SessionServices(
                    manager, conversation_service=ConversationService(manager)
                ),
                outbound=SimpleNamespace(dispatch=dispatch),
                event_bus=bus,
            )
        )

    return HostConversation(build, affection, reply_policy)


async def test_deliver_uses_the_generation_published_for_that_call(tmp_path) -> None:
    first_store = SessionManager(tmp_path / "first")
    second_store = SessionManager(tmp_path / "second")
    for manager in (first_store, second_store):
        manager.get_or_create("role:mira").metadata.update(
            role_id="mira", role_runtime_config={"mood_catalog": ["想你"]}
        )
    first_bus = EventBus()
    second_bus = EventBus()
    runtime = _Runtime(
        SimpleNamespace(conversation=_host_conversation(first_store, first_bus))
    )
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
        )

    try:
        await runner.deliver(reply("第一代"))
        runtime.core = SimpleNamespace(
            conversation=_host_conversation(second_store, second_bus)
        )
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


def test_core_modules_publish_the_proactive_port_and_conversation() -> None:
    host = object()
    conversation = object()
    bus = EventBus()
    provided: dict[str, object] = {}

    def collect(key, impl) -> None:
        provided[key.name] = impl

    inputs = PluginCoreInputs(
        plugin_dirs=(),
        event_bus=bus,
        rpc=SimpleNamespace(),
        workspace=None,
        tools=None,
        role_store=None,
        session_manager=None,
        role_runtime_registry=None,
        provider=None,
        model=None,
        light_provider=None,
        light_model=None,
        external_turns=None,
        background_results=None,
        http=None,
        process_resources=None,
        proactive_host=host,
        conversation=conversation,
    )
    for module in plugin_core_modules(inputs):
        module(collect)
    assert provided["proactive_host"] is host
    assert provided["conversation"] is conversation
