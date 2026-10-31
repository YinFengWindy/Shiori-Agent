"""Initiated delivery: one reply, its target, and a natural sequence."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from agent.looping.ports import SessionServices
from agent.turns.channel_sequence import ChannelSequenceOwner
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import DeliveryReceipt
from bus.event_bus import EventBus
from bus.events_lifecycle import InitiatedMessageCommitted
from bus.queue import MessageBus
from conversation.initiated import bound_turn_getters, commit_initiated_reply
from conversation.service import ConversationService
from core.roles.affection_access import AffectionGetter
from core.roles.reply_policy import ReplyPolicyGetter
from core.roles.reply_state import InvalidRoleReply
from core.roles.store import RoleStore
from session.manager import SessionManager
from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.core.conversation import (
    InitiatedDelivery,
    InitiatedReply,
    InitiatedToolFact,
)
from shiori_sdk.messages import InboundMessage


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
        "expected_mood_updated_at": "",
        "moods": ("想你",),
    }
    fields.update(overrides)
    return InitiatedReply(**fields)


def _natural_roles(tmp_path) -> RoleStore:
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="米拉",
        system_prompt="规矩",
        runtime_config={"natural_chat_enabled": True, "mood_catalog": ["想你"]},
    )
    return roles


async def test_desktop_reply_stores_media_and_mood_and_reports_its_id(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata.update(
        role_id="mira", role_runtime_config={"mood_catalog": ["想你"]}
    )
    bus = EventBus()
    events: list[InitiatedMessageCommitted] = []
    bus.on(InitiatedMessageCommitted, events.append)
    sent = []
    orchestrator = _orchestrator(manager, bus, _recording_outbound(sent))
    try:
        with _getters(policy=None):
            delivery = await commit_initiated_reply(
                orchestrator, _reply(media=("pic.png",))
            )
    finally:
        await bus.aclose()
    rows = manager._store.fetch_session_messages("role:mira")
    assert rows[0]["content"] == "带伞"
    assert rows[0]["media"] == ["pic.png"]
    assert rows[0]["metadata"]["mood"] == "想你"
    assert rows[0]["metadata"]["thought"] == "我想你"
    assert delivery == InitiatedDelivery(message_ids=(rows[0]["id"],), complete=True)
    assert len(events) == 1
    event = events[0]
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


async def test_reply_older_than_the_stored_mood_is_dropped(tmp_path) -> None:
    """A passive reply stored a newer mood while the tick was thinking."""
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata.update(
        role_id="mira",
        role_runtime_config={"mood_catalog": ["想你", "开心"]},
        current_mood="开心",
        current_mood_updated_at="2026-10-31T00:05:00+00:00",
    )
    bus = EventBus()
    sent = []
    orchestrator = _orchestrator(manager, bus, _recording_outbound(sent))
    stale = _reply(
        expected_mood_updated_at="2026-10-31T00:00:00+00:00", moods=("想你", "开心")
    )
    try:
        with _getters(policy=None):
            with pytest.raises(ValueError, match="角色已有更新的正式回复"):
                await commit_initiated_reply(orchestrator, stale)
    finally:
        await bus.aclose()
    assert sent == []
    assert manager._store.fetch_session_messages("role:mira") == []
    assert manager.get_or_create("role:mira").metadata["current_mood"] == "开心"


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
        account_channel="telegram",
        account_target=AccountTarget("private", "user-1"),
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
    roles = _natural_roles(tmp_path)
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata["role_id"] = "mira"
    bus = EventBus()
    events: list[InitiatedMessageCommitted] = []
    bus.on(InitiatedMessageCommitted, events.append)
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
            delivery = await commit_initiated_reply(orchestrator, reply)
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
    texts = [row for row in rows if row["content"]]
    assert delivery == InitiatedDelivery(
        message_ids=tuple(row["id"] for row in texts), complete=True
    )
    assert len(events) == 1
    assert events[0].message_id == texts[-1]["id"]
    assert events[0].tools_used == ("message_push",)
    assert events[0].source == "drift"


async def test_interrupted_sequence_reports_the_stored_prefix(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user message after the first text drops the rest; the result says so."""
    paused = asyncio.Event()

    async def pace(_seconds: float) -> None:
        paused.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", pace)
    roles = _natural_roles(tmp_path)
    manager = SessionManager(tmp_path)
    manager.get_or_create("role:mira").metadata["role_id"] = "mira"
    bus = EventBus()
    sent = []
    orchestrator = _orchestrator(manager, bus, _recording_outbound(sent), roles=roles)
    batches = ChannelSequenceOwner()
    reply = _reply(content="先说一句\n\n再说一句", messages=("先说一句", "再说一句"))

    async def deliver() -> InitiatedDelivery:
        with _getters(policy=object()), batches.bind(MessageBus()):
            return await commit_initiated_reply(orchestrator, reply)

    task = asyncio.create_task(deliver())
    try:
        await asyncio.wait_for(paused.wait(), 3)
        batches.interrupt_background(
            InboundMessage(
                "desktop", "user", "role:mira", "等等", metadata={"role_id": "mira"}
            )
        )
        delivery = await asyncio.wait_for(task, 3)
    finally:
        await bus.aclose()
    [row] = manager._store.fetch_session_messages("role:mira")
    assert [message.content for message in sent] == ["先说一句"]
    assert delivery == InitiatedDelivery(message_ids=(row["id"],), complete=False)


async def test_sequence_requires_natural_chat(tmp_path) -> None:
    roles = _natural_roles(tmp_path)
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
    roles = _natural_roles(tmp_path)
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
        account_channel="telegram",
        account_target=AccountTarget("private", "user-1"),
    )
    try:
        with _getters(policy=object()), ChannelSequenceOwner().bind(MessageBus()):
            with pytest.raises(RuntimeError, match="账号目标发送服务不可用"):
                await commit_initiated_reply(orchestrator, reply)
    finally:
        await bus.aclose()
    assert manager._store.fetch_session_messages("role:mira") == []
    assert sent_text == []
