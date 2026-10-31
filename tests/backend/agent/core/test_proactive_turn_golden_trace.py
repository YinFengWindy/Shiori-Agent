"""Golden trace of a proactive tick with the production assembly (#907 P6b-0).

P6b moves the proactive loop, its tick, delivery and Drift into a plugin.
These scenarios record what one tick does today, seen only from outside:
what the transport (desktop sender or the account's platform send) received
and when, the messages and mood the role session holds afterwards, the
``InitiatedMessageCommitted`` events on the domain bus, the session presence,
what the affection socket was told, the Drift state file, and which tools the
model was offered. They never name a phase, gate, pipeline or tool module, so
the moved code must pass them unchanged.

Allowed edits during P6b: ``proactive_host`` (the assembly: today
``build_proactive_runtime`` and the role tick dispatcher, later the plugin),
``_seed_role`` and ``_bind_private_chat`` (how the role is switched on and
bound; PR5 moves the proactive switch from ``roles.update`` to the plugin's
settings) and ``ProactiveHost.tick`` (how one tick is driven), plus the event and
affection method names where #907 renames them on purpose
(``InitiatedMessageCommitted``, ``handle_initiated_sent``). Scenario
assertions stay as they are.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.account_delivery import AccountDelivery
from agent.config_models import Config
from agent.core.proactive_turn.strategies import RelationshipStrategy
from agent.core.turn_events import core_kernel
from agent.provider import LLMProvider, LLMResponse, ToolCall
from agent.tools.account_delivery import AccountSendTool
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.turns.channel_sequence import ChannelSequenceOwner
from agent.proactive_host import HostProactiveRunner
from bootstrap.proactive import build_proactive_runtime
from bus.event_bus import EventBus
from bus.events_lifecycle import InitiatedMessageCommitted
from bus.queue import MessageBus
from conversation.service import desktop_thread_id
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.desktop_presence import DesktopPresence
from core.identity import IdentityChat
from core.memory.group_environment import GroupEnvironment
from core.roles import RoleRepository, RoleRuntimeRegistry, RoleStore
from core.roles.affection_access import AffectionGetter
from plugins.natural_chat.backend.plugin import NaturalChatPolicy
from shiori_sdk.core.affection import Affection
from proactive_v2.loop import ProactiveLoop
from session.manager import SessionManager
from tests.support.generation_getters import turn_getters
from tests.support.push import allow_every_role_target

ROLE_PROMPT = "你是 Mira，说话温柔。"
SESSION_KEY = "role:mira"
MOOD, THOUGHT = "平静", "我有点想他，想问问他在做什么。"
# The bound user's private chat through the role's ``chat`` account.
BOUND_CHAT = ("chat", "dm:user-1")


class ScriptedProvider(LLMProvider):
    """Answers chat requests from ``script`` in order and records them."""

    def __init__(self) -> None:
        super().__init__(
            api_key="test", model_context_window=128000, default_max_tokens=512
        )
        self.script: list[LLMResponse] = []
        self.requests: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> LLMResponse:  # type: ignore[override]
        self.requests.append(kwargs)
        return self.script.pop(0)

    def offered(self, request: int) -> set[str]:
        """Names of the tools offered in request ``request``."""
        return {
            tool["function"]["name"] for tool in self.requests[request]["tools"] or []
        }


class RecordingAffection:
    """The ``AFFECTION`` socket: says whether the role is lonely, records sends."""

    def __init__(self) -> None:
        self.lonely = True
        self.sent: list[str] = []

    def render_prompt(self, role_id: str) -> str | None:
        return None

    def should_trigger_proactive(
        self, session_key: str, now: datetime
    ) -> tuple[bool, dict[str, Any]]:
        return self.lonely, {"reason": "golden"}

    def handle_initiated_sent(self, session_key: str) -> None:
        self.sent.append(session_key)


@dataclass(frozen=True)
class Delivered:
    """One transport send and how many role messages were stored before it.

    ``owner_commits`` is the desktop transport contract: True when the send is
    marked ``pending_commit``, so the desktop bridge leaves storing the message
    to the turn owner instead of storing it a second time. Account sends have
    no such contract and record None.
    """

    channel: str
    chat_id: str
    text: str
    stored_before: int
    owner_commits: bool | None


class _ModelRuntime:
    """A role model resolver that leaves the provider as configured."""

    def activate(self, role_id: str, purpose: str):
        return nullcontext(SimpleNamespace(model="role-model"))


@dataclass
class ProactiveHost:
    """One proactive role ``mira``; the scenarios read only these fields."""

    workspace: Path
    provider: ScriptedProvider
    affection: RecordingAffection
    desktop_presence: DesktopPresence
    loop: ProactiveLoop
    delivered: list[Delivered] = field(default_factory=list[Delivered])
    events: list[InitiatedMessageCommitted] = field(
        default_factory=list[InitiatedMessageCommitted]
    )
    # Per event: whether its message_id was already stored when it arrived
    # (the desktop bridge looks the message up by that id).
    events_after_store: list[bool] = field(default_factory=list[bool])
    # Ticks that failed; the runtime loop logs them and keeps running.
    tick_errors: list[Exception] = field(default_factory=list[Exception])
    busy: bool = False
    # Raised by the desktop sender instead of sending, while set.
    desktop_failure: Exception | None = None

    async def tick(self) -> None:
        """Runs one proactive tick as the runtime does for a due role.

        The natural_chat plugin is on, as by default; the role's own flag
        decides whether the tick replies naturally. Like the runtime loop, a
        failed tick is kept (in ``tick_errors``) rather than raised.
        """
        with (
            turn_getters(affection=self.affection, policy=NaturalChatPolicy()),
            ChannelSequenceOwner().bind(MessageBus()),
        ):
            try:
                _ = await self.loop._run_tick()  # pyright: ignore[reportPrivateUsage]
            except Exception as error:
                self.tick_errors.append(error)

    def stored(self) -> list[dict[str, Any]]:
        """The role session's assistant messages as reloaded from disk."""
        session = SessionManager(self.workspace).get_or_create(SESSION_KEY)
        return [m for m in session.messages if m["role"] == "assistant"]

    def mood(self) -> str:
        """The role's current mood as reloaded from disk."""
        session = SessionManager(self.workspace).get_or_create(SESSION_KEY)
        return str(session.metadata.get("current_mood") or "")

    def last_initiated_at(self) -> datetime | None:
        """When the session presence last recorded a proactive send."""
        return SessionManager(self.workspace).presence.last_initiated_at(SESSION_KEY)


def _seed_role(workspace: Path, *, natural: bool) -> RoleStore:
    roles = RoleStore(workspace)
    _ = roles.create_role(
        role_id="mira",
        name="Mira",
        system_prompt=ROLE_PROMPT,
        runtime_config={"natural_chat_enabled": natural},
    )
    _ = roles.update_role("mira", proactive={"enabled": True})
    sessions = SessionManager(workspace)
    sessions.save(
        sessions.open_role_session(
            "mira",
            role_name="Mira",
            role_runtime_config={"natural_chat_enabled": natural},
        )
    )
    return roles


def _bind_private_chat(roles: RoleStore) -> None:
    """An online ``chat`` account of mira paired with the user in ``BOUND_CHAT``."""
    account = roles.accounts.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="bot",
        config_ref="bot",
        role_id="mira",
        token="live",
    )
    _ = roles.accounts.report(account.record.id, "live", connection="online")
    _ = roles.identities.pair(
        roles.identities.create_pairing_code().code,
        record=account.record,
        user_id="user-1",
        scope="account",
        chat=IdentityChat(account.record.id, *BOUND_CHAT),
    )


@asynccontextmanager
async def proactive_host(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, *, natural: bool = False
) -> AsyncGenerator[ProactiveHost]:
    """The production proactive runtime of one enabled role, ticked by hand.

    Model, desktop sender, account platform and affection plugin are fakes;
    sessions, presence, roles, accounts, identities, the proactive state
    store and the Drift state are real files under ``workspace``.
    """
    roles = _seed_role(workspace, natural=natural)
    sessions = SessionManager(workspace)
    provider = ScriptedProvider()
    affection = RecordingAffection()
    desktop_presence = DesktopPresence()
    bus = EventBus()
    holder: dict[str, ProactiveHost] = {}

    def stored_now() -> int:
        return len(holder["host"].stored())

    async def desktop_send(chat_id: str, text: str, metadata: dict[str, object]) -> str:
        host = holder["host"]
        if host.desktop_failure is not None:
            raise host.desktop_failure
        owner_commits = metadata.get("pending_commit") is True
        host.delivered.append(
            Delivered("desktop", chat_id, text, stored_now(), owner_commits)
        )
        return f"desktop-{len(host.delivered)}"

    async def platform_send(payload: dict[str, Any]) -> dict[str, Any]:
        host = holder["host"]
        host.delivered.append(
            Delivered(
                "chat",
                f"{payload['target_kind']}:{payload['target_id']}",
                str(payload["message"]),
                stored_now(),
                None,
            )
        )
        return {"message_id": f"platform-{len(host.delivered)}"}

    def platform_rpc(_method: str) -> tuple[str, Any]:
        return "chat", platform_send

    def passive_busy(_session_key: str) -> bool:
        return holder["host"].busy

    push = MessagePushTool(role_target_validator=allow_every_role_target)
    push.register_channel("desktop", text_with_metadata=desktop_send)
    tools = ToolRegistry()
    tools.register(
        AccountSendTool(
            AccountDelivery(
                roles.accounts,
                cast(Any, SimpleNamespace(resolve=platform_rpc)),
                AccountDeliveryLedger(workspace),
                roles.identities,
            ),
            bus,
        )
    )
    _bind_private_chat(roles)
    registry = RoleRuntimeRegistry(
        RoleRepository(roles), model_resolver=cast(Any, _ModelRuntime())
    )
    # A hand-driven tick has no generation lease, so the port pins this one.
    # Natural replies bind ``reply_sequences`` on that lease.
    reply_sequences = ChannelSequenceOwner()
    agent_loop = SimpleNamespace(
        role_runtime_registry=registry,
        processing_state=SimpleNamespace(is_busy=passive_busy),
        tools=tools,
        bus=MessageBus(),
    )
    group_environment = GroupEnvironment(workspace, sessions.conversation_store)
    # The published generation the port pins. Desktop presence and the busy
    # flag are the ones the scenarios mutate.
    published = SimpleNamespace(
        role_runtime_registry=registry,
        loop=agent_loop,
        group_environment=group_environment,
        desktop_presence=desktop_presence,
    )

    class _PublishedRuntime:
        def __init__(self) -> None:
            self.core = published
            self.desktop_presence = desktop_presence

        def acquire(self) -> Any:
            runtime = self

            class _Lease:
                def __init__(self) -> None:
                    self.core = runtime.core
                    self.reply_sequences = reply_sequences

                async def __aenter__(self) -> Any:
                    return self

                async def __aexit__(self, *_exc: object) -> None:
                    return None

            return _Lease()

        async def wait_for_admission(self) -> None:
            return None

    affection_getter = AffectionGetter()
    affection_getter.bind(lambda: cast(Affection, affection))
    # The production presence of this session store (bootstrap/tools.py).
    presence = sessions.presence
    tasks, loops = (  # pyright: ignore[reportUnknownVariableType]
        build_proactive_runtime(
            Config(provider="test", model="m", api_key=""),
            workspace,
            session_manager=sessions,
            provider=provider,
            light_provider=provider,
            push_tool=push,
            memory_store=None,
            presence=presence,
            agent_loop=cast(Any, agent_loop),
            kernel=core_kernel,
            proactive_motives=[RelationshipStrategy(affection_getter)],
            event_bus=bus,
            proactive_host=HostProactiveRunner(lambda: _PublishedRuntime()),
            group_environment=group_environment,
        )
    )
    for task in cast(list[Coroutine[Any, Any, None]], tasks):
        task.close()  # the loops are ticked by hand, never run
    host = ProactiveHost(
        workspace, provider, affection, desktop_presence, loops["mira"]
    )
    holder["host"] = host

    def committed(event: InitiatedMessageCommitted) -> None:
        host.events.append(event)
        stored_ids = {str(message["id"]) for message in host.stored()}
        host.events_after_store.append(event.message_id in stored_ids)

    bus.on(InitiatedMessageCommitted, committed)

    # Natural messages are paced like typing; the golden trace does not wait.
    async def no_pause(_: object) -> None:
        return None

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", no_pause)
    try:
        yield host
    finally:
        await registry.close_all()
        await bus.aclose()


def _call(name: str, arguments: dict[str, Any], raw: str | None = None):
    return LLMResponse(content="", tool_calls=[ToolCall(name, name, arguments, raw)])


def _push(message: str) -> LLMResponse:
    return _call("message_push", {"message": message, "mood": MOOD, "thought": THOUGHT})


def _natural_push(messages: list[str]) -> LLMResponse:
    raw = json.dumps({"messages": messages}, ensure_ascii=False)
    arguments: dict[str, Any] = {"messages": messages, "mood": MOOD, "thought": THOUGHT}
    return _call("message_push", arguments, raw)


_REPLY = _call("finish_turn", {"decision": "reply"})


def _assert_one_event(host: ProactiveHost, *, channel: str, chat_id: str) -> None:
    """The single committed event names the last stored message and its text."""
    stored = host.stored()
    [event] = host.events
    assert (event.session_key, event.role_id, event.channel, event.chat_id) == (
        SESSION_KEY,
        "mira",
        channel,
        chat_id,
    )
    assert event.thread_id == stored[-1]["metadata"]["thread_id"]
    assert event.message_id == stored[-1]["id"]
    assert event.assistant_response == "\n\n".join(m["content"] for m in stored)
    assert event.tools_used == ("message_push",)
    assert host.events_after_store == [True]


async def scenario_lonely_tick_speaks_on_desktop(host: ProactiveHost) -> None:
    """A lonely role with nothing to share reaches out once on the desktop.

    The text is sent before anything is stored, the stored message carries the
    proactive source and the reply's mood and thought, the role's mood follows,
    and presence, affection and the bus each hear of it once.
    """
    host.provider.script = [_push("在忙吗？想你了。"), _REPLY]
    before = datetime.now(timezone.utc)

    await host.tick()

    assert host.delivered == [
        Delivered("desktop", SESSION_KEY, "在忙吗？想你了。", 0, True)
    ]
    [message] = host.stored()
    assert (message["content"], message["proactive"], message["tools_used"]) == (
        "在忙吗？想你了。",
        True,
        ["message_push"],
    )
    metadata = message["metadata"]
    assert (metadata["source"], metadata["chat_type"], metadata["role_id"]) == (
        "proactive",
        "desktop",
        "mira",
    )
    assert metadata["thread_id"] == desktop_thread_id("mira")
    assert (metadata["mood"], metadata["thought"]) == (MOOD, THOUGHT)
    assert host.mood() == MOOD
    _assert_one_event(host, channel="desktop", chat_id=SESSION_KEY)
    last = host.last_initiated_at()
    assert last is not None and last >= before
    assert host.affection.sent == [SESSION_KEY]
    # The model saw the role and was offered the push and the closing decision.
    assert ROLE_PROMPT in str(host.provider.requests[0]["messages"][0]["content"])
    assert {"message_push", "finish_turn"} <= host.provider.offered(0)
    assert len(host.provider.requests) == 2


async def scenario_natural_reply_sends_each_message(host: ProactiveHost) -> None:
    """Natural chat: the message list goes out in order, each one stored.

    Every message is sent before it is stored, all of them share one reply
    sequence, and the turn commits one event naming the last message.
    """
    messages = ["在吗？", "外面下雨了，记得带伞。"]
    host.provider.script = [_natural_push(messages), _REPLY]

    await host.tick()

    assert host.delivered == [
        Delivered("desktop", SESSION_KEY, "在吗？", 0, True),
        Delivered("desktop", SESSION_KEY, "外面下雨了，记得带伞。", 1, True),
    ]
    stored = host.stored()
    assert [m["content"] for m in stored] == messages
    assert [m["metadata"]["reply_sequence_index"] for m in stored] == [0, 1]
    assert len({m["metadata"]["reply_sequence_id"] for m in stored}) == 1
    assert all(
        m["proactive"] and m["metadata"]["source"] == "proactive" for m in stored
    )
    assert host.mood() == MOOD
    _assert_one_event(host, channel="desktop", chat_id=SESSION_KEY)
    assert host.affection.sent == [SESSION_KEY]
    assert host.last_initiated_at() is not None


async def scenario_away_user_is_reached_in_bound_private_chat(
    host: ProactiveHost,
) -> None:
    """Away from the desktop, the message goes to the bound user's private chat.

    It goes through the role's account to the paired user, and the stored
    message records the platform receipt and the private thread.
    """
    host.desktop_presence.report(False)
    host.provider.script = [_push("到家了吗？"), _REPLY]

    await host.tick()

    assert host.delivered == [
        Delivered("chat", "private:user-1", "到家了吗？", 0, None)
    ]
    [message] = host.stored()
    assert (message["delivery_status"], message["external_message_id"]) == (
        "sent",
        "platform-1",
    )
    assert message["metadata"]["chat_type"] == "private"
    assert (message["proactive"], message["metadata"]["source"]) == (True, "proactive")
    assert host.mood() == MOOD
    assert message["metadata"]["thread_id"] == "thread:mira:chat:dm:user-1"
    _assert_one_event(host, channel=BOUND_CHAT[0], chat_id=BOUND_CHAT[1])
    assert host.affection.sent == [SESSION_KEY]


async def scenario_model_skip_sends_nothing(host: ProactiveHost) -> None:
    """The model decides the user is busy: nothing is sent, stored or announced."""
    host.provider.script = [
        _call("finish_turn", {"decision": "skip", "reason": "user_busy"})
    ]

    await host.tick()

    assert len(host.provider.requests) == 1
    assert host.delivered == []
    assert host.stored() == []
    assert host.events == []
    assert host.affection.sent == []
    assert host.last_initiated_at() is None
    assert host.mood() == ""


async def scenario_busy_role_never_asks_the_model(host: ProactiveHost) -> None:
    """While the role is answering the user, a due tick does nothing at all."""
    host.busy = True

    await host.tick()

    assert host.provider.requests == []
    assert host.delivered == []
    assert host.stored() == []
    assert host.events == []
    assert host.affection.sent == []


async def scenario_repeated_message_is_not_sent_again(host: ProactiveHost) -> None:
    """The same message on a later tick (within a day) is dropped before sending."""
    host.provider.script = [_push("早安！"), _REPLY, _push("早安！"), _REPLY]

    await host.tick()
    await host.tick()

    assert [d.text for d in host.delivered] == ["早安！"]
    assert [m["content"] for m in host.stored()] == ["早安！"]
    assert len(host.events) == 1
    assert host.affection.sent == [SESSION_KEY]
    assert len(host.provider.requests) == 4


async def scenario_failed_send_keeps_nothing_and_retries(host: ProactiveHost) -> None:
    """A send that fails stores and announces nothing; the next tick sends it.

    The tick fails (the runtime loop logs it and carries on), and the failed
    text is not counted as sent, so the identical message is not suppressed
    afterwards.
    """
    host.desktop_failure = ConnectionError("桌面端未连接")
    host.provider.script = [_push("你还好吗？"), _REPLY]

    await host.tick()

    assert host.tick_errors
    host.tick_errors.clear()
    assert host.delivered == []
    assert host.stored() == []
    assert host.events == []
    assert host.affection.sent == []
    assert host.last_initiated_at() is None
    assert host.mood() == ""

    host.desktop_failure = None
    host.provider.script = [_push("你还好吗？"), _REPLY]
    await host.tick()

    assert [d.text for d in host.delivered] == ["你还好吗？"]
    assert len(host.events) == 1


async def scenario_idle_drift_shares_and_records_run(host: ProactiveHost) -> None:
    """Not lonely and nothing to share: the role drifts with its own skill.

    It sends one message from the Drift run, which is stored and announced like
    any proactive message; the run is recorded in the role's Drift state, and a
    second tick soon after does not drift again.
    """
    # A workspace skill of the role: finishing a built-in skill writes its
    # state.json next to the built-in SKILL.md, i.e. into the source tree.
    skill = host.workspace / "roles/mira/drift/skills/golden-walk"
    skill.mkdir(parents=True)
    _ = (skill / "SKILL.md").write_text(
        "---\nname: golden-walk\ndescription: 出门散步\n---\n散步时想到什么就说。\n",
        "utf-8",
    )
    host.affection.lonely = False
    finish = {
        "skill_used": "golden-walk",
        "one_line": "散步时分享了晚霞",
        "next": "明天换条路",
        "message_result": "sent",
    }
    host.provider.script = [_push("今天的晚霞好好看。"), _call("finish_drift", finish)]

    await host.tick()

    assert host.delivered == [
        Delivered("desktop", SESSION_KEY, "今天的晚霞好好看。", 0, True)
    ]
    [message] = host.stored()
    assert (message["content"], message["proactive"]) == ("今天的晚霞好好看。", True)
    assert message["metadata"]["source"] == "proactive"
    _assert_one_event(host, channel="desktop", chat_id=SESSION_KEY)
    assert host.affection.sent == [SESSION_KEY]
    assert {"message_push", "finish_drift"} <= host.provider.offered(0)
    drift = json.loads(
        (host.workspace / "roles/mira/drift/drift.json").read_text("utf-8")
    )
    [run] = drift["recent_runs"]
    assert (run["skill"], run["one_line"], run["message_result"]) == (
        "golden-walk",
        "散步时分享了晚霞",
        "sent",
    )
    state = json.loads((skill / "state.json").read_text("utf-8"))
    assert (state["run_count"], state["next"]) == (1, "明天换条路")

    await host.tick()

    assert len(host.provider.requests) == 2
    assert len(host.delivered) == 1


Scenario = Callable[[ProactiveHost], Awaitable[None]]


@pytest.mark.parametrize(
    ("scenario", "natural"),
    [
        (scenario_lonely_tick_speaks_on_desktop, False),
        (scenario_natural_reply_sends_each_message, True),
        (scenario_away_user_is_reached_in_bound_private_chat, False),
        (scenario_model_skip_sends_nothing, False),
        (scenario_busy_role_never_asks_the_model, False),
        (scenario_repeated_message_is_not_sent_again, False),
        (scenario_failed_send_keeps_nothing_and_retries, False),
        (scenario_idle_drift_shares_and_records_run, False),
    ],
    ids=lambda value: (
        value.__name__.removeprefix("scenario_") if callable(value) else None
    ),
)
async def test_proactive_turn_golden_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: Scenario,
    natural: bool,
) -> None:
    async with proactive_host(tmp_path, monkeypatch, natural=natural) as host:
        await scenario(host)
        # A scenario that expects a failed tick clears what it checked.
        assert host.tick_errors == []
