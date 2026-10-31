"""Initiated delivery: one reply, its target, and a natural sequence."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agent.looping.ports import SessionServices
from agent.turns.channel_sequence import ChannelSequenceOwner
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import DeliveryReceipt
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted
from bus.queue import MessageBus
from conversation.initiated import bound_turn_getters, commit_initiated_reply
from conversation.service import ConversationService
from core.roles.affection_access import AffectionGetter
from core.roles.reply_policy import ReplyPolicyGetter
from core.roles.reply_state import InvalidRoleReply
from core.roles.store import RoleStore
from session.manager import SessionManager
from shiori_sdk.core.conversation import (
    InitiatedAccountTarget,
    InitiatedMessageCommitted,
    InitiatedReply,
    InitiatedToolFact,
)


@contextmanager
def _getters(*, policy: object | None):
    affection = AffectionGetter()
    affection.bind(lambda: None)
    reply_policy = ReplyPolicyGetter()
    reply_policy.bind(lambda: policy)
    with bound_turn_getters(affection, reply_policy):
        yield


def _recording_outbound(sent: list):
    async def dispatch(message):
        sent.append(message)
        return DeliveryReceipt.sent()

    return SimpleNamespace(dispatch=dispatch)


def _orchestrator(manager: SessionManager, bus: EventBus, outbound, *, roles=None):
    return TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                manager, conversation_service=ConversationService(manager)
            ),
            outbound=outbound,
            event_bus=bus,
            role_lookup=None if roles is None else roles.get_role,
        )
    )


def _reply(**overrides) -> InitiatedReply:
    fields = {
        "session_key": "role:mira",
        "content": "带伞",
        "source": "drift",
        "channel": "desktop",
        "chat_id": "role:mira",
        "mood": "想你",
        "thought": "我想你",
    }
    fields.update(overrides)
    return InitiatedReply(**fields)


async def test_desktop_reply_stores_media_and_mood_under_the_old_event_name(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata.update(
        role_id="mira", role_runtime_config={"mood_catalog": ["想你"]}
    )
    bus = EventBus()
    events: list[ProactiveMessageCommitted] = []
    bus.on(ProactiveMessageCommitted, events.append)
    sent = []
    orchestrator = _orchestrator(manager, bus, _recording_outbound(sent))
    try:
        with _getters(policy=None):
            message_id = await commit_initiated_reply(
                orchestrator, _reply(media=("pic.png",))
            )
    finally:
        await bus.aclose()
    rows = manager._store.fetch_session_messages("role:mira")
    assert rows[0]["content"] == "带伞"
    assert rows[0]["media"] == ["pic.png"]
    assert rows[0]["metadata"]["mood"] == "想你"
    assert rows[0]["metadata"]["thought"] == "我想你"
    assert message_id == rows[0]["id"]
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, InitiatedMessageCommitted)
    assert event.source == "drift"
    assert event.channel == "desktop"
    assert event.chat_id == "role:mira"
    assert event.role_id == "mira"
    assert event.assistant_response == "带伞"
    assert event.message_id == rows[0]["id"]
    assert event.tools_used == ("message_push",)
    assert sent[0].media == ["pic.png"]


async def test_mood_outside_the_catalog_stores_nothing(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata.update(
        role_id="mira", role_runtime_config={"mood_catalog": ["想你"]}
    )
    bus = EventBus()
    sent = []
    orchestrator = _orchestrator(manager, bus, _recording_outbound(sent))
    try:
        with _getters(policy=None):
            with pytest.raises(InvalidRoleReply):
                await commit_initiated_reply(orchestrator, _reply(mood="平静"))
    finally:
        await bus.aclose()
    assert manager._store.fetch_session_messages("role:mira") == []
    assert sent == []


async def test_account_target_without_delivery_does_not_fall_back_to_desktop(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata.update(
        role_id="mira", role_runtime_config={"mood_catalog": ["想你"]}
    )
    bus = EventBus()
    sent = []
    orchestrator = _orchestrator(manager, bus, _recording_outbound(sent))
    reply = _reply(
        channel="telegram",
        chat_id="dm-1",
        account_target=InitiatedAccountTarget(
            account_channel="telegram",
            target_kind="private",
            target_id="user-1",
        ),
    )
    try:
        with _getters(policy=None):
            with pytest.raises(RuntimeError, match="账号目标发送服务不可用"):
                await commit_initiated_reply(orchestrator, reply)
    finally:
        await bus.aclose()
    assert manager._store.fetch_session_messages("role:mira") == []
    assert sent == []


async def test_tool_facts_without_a_sequence_are_rejected(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    bus = EventBus()
    orchestrator = _orchestrator(manager, bus, None)
    reply = _reply(
        tool_facts=(
            InitiatedToolFact(
                call_id="c1", name="weather", arguments={"city": "杭州"}, result="有雨"
            ),
        )
    )
    try:
        with pytest.raises(ValueError, match="工具事实只能随自然回复序列保存"):
            await commit_initiated_reply(orchestrator, reply)
    finally:
        await bus.aclose()
    assert manager._store.fetch_session_messages("role:mira") == []


async def test_sequence_content_must_match_the_messages(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    bus = EventBus()
    orchestrator = _orchestrator(manager, bus, None)
    try:
        with pytest.raises(ValueError, match="主动草稿与已校验消息列表不一致"):
            await commit_initiated_reply(
                orchestrator,
                _reply(content="只有一句", messages=("先说一句", "再说一句")),
            )
    finally:
        await bus.aclose()
    assert manager._store.fetch_session_messages("role:mira") == []


async def test_natural_sequence_stores_each_message_and_the_tool_fact(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_pause(_seconds: float) -> None:
        return None

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", _no_pause)
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="米拉",
        system_prompt="规矩",
        runtime_config={"natural_chat_enabled": True, "mood_catalog": ["想你"]},
    )
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata["role_id"] = "mira"
    bus = EventBus()
    events: list[ProactiveMessageCommitted] = []
    bus.on(ProactiveMessageCommitted, events.append)
    sent_text = []

    async def dispatch(message):
        sent_text.append(message.content)
        return DeliveryReceipt.sent()

    orchestrator = _orchestrator(
        manager, bus, SimpleNamespace(dispatch=dispatch), roles=roles
    )
    reply = _reply(
        content="先说一句\n\n再说一句",
        messages=("先说一句", "再说一句"),
        tool_facts=(
            InitiatedToolFact(
                call_id="c1", name="weather", arguments={"city": "杭州"}, result="有雨"
            ),
        ),
    )
    try:
        with _getters(policy=object()), ChannelSequenceOwner().bind(MessageBus()):
            message_id = await commit_initiated_reply(orchestrator, reply)
    finally:
        await bus.aclose()
    rows = manager._store.fetch_session_messages("role:mira")
    assert [row["content"] for row in rows if row["content"]] == [
        "先说一句",
        "再说一句",
    ]
    assert sent_text == ["先说一句", "再说一句"]
    fact = next(row for row in rows if row.get("tool_chain"))
    assert fact["tool_chain"][0]["calls"][0]["name"] == "weather"
    last = next(row for row in rows if row["content"] == "再说一句")
    assert len(events) == 1
    assert events[0].message_id == last["id"] == message_id
    assert events[0].tools_used == ("message_push",)
    assert events[0].source == "drift"


async def test_sequence_requires_natural_chat(tmp_path) -> None:
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="米拉",
        system_prompt="规矩",
        runtime_config={"natural_chat_enabled": True, "mood_catalog": ["想你"]},
    )
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata["role_id"] = "mira"
    bus = EventBus()
    orchestrator = _orchestrator(manager, bus, None, roles=roles)
    try:
        with _getters(policy=None):
            with pytest.raises(RuntimeError, match="自然回复序列需要角色开启自然聊天"):
                await commit_initiated_reply(
                    orchestrator,
                    _reply(
                        content="先说一句\n\n再说一句",
                        messages=("先说一句", "再说一句"),
                    ),
                )
    finally:
        await bus.aclose()
    assert manager._store.fetch_session_messages("role:mira") == []


async def test_sequence_account_target_is_not_sent_as_desktop(tmp_path) -> None:
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="米拉",
        system_prompt="规矩",
        runtime_config={"natural_chat_enabled": True, "mood_catalog": ["想你"]},
    )
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata["role_id"] = "mira"
    bus = EventBus()
    sent_text = []

    async def dispatch(message):
        sent_text.append(message.content)
        return DeliveryReceipt.sent()

    orchestrator = _orchestrator(
        manager, bus, SimpleNamespace(dispatch=dispatch), roles=roles
    )
    reply = _reply(
        content="先说一句\n\n再说一句",
        messages=("先说一句", "再说一句"),
        account_target=InitiatedAccountTarget(
            account_channel="telegram",
            target_kind="private",
            target_id="user-1",
        ),
    )
    try:
        with _getters(policy=object()), ChannelSequenceOwner().bind(MessageBus()):
            with pytest.raises(RuntimeError, match="账号目标发送服务不可用"):
                await commit_initiated_reply(orchestrator, reply)
    finally:
        await bus.aclose()
    assert manager._store.fetch_session_messages("role:mira") == []
    assert sent_text == []
