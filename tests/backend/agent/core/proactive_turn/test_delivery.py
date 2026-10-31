from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.core.proactive_turn import ResolveResult
from agent.core.proactive_turn.delivery import (
    deliver_execute,
    resolve_target_transport,
)
from agent.turns.result import TurnOutbound, TurnResult
from bus.event_bus import EventBus
from bus.events_lifecycle import InitiatedMessageCommitted
from core.roles.reply_state import RoleReply, RoleReplyContext
from proactive_v2.context import AgentTickContext
from proactive_v2.gateway import GatewayDeps
from proactive_v2.tools import ToolDeps
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from tests.backend.proactive_v2.conftest import (
    FakeAckSink,
    FakeLLM,
    FakeStateStore,
    make_proactive_pipeline,
)


def _pipeline(*, host):
    return SimpleNamespace(
        _session_key="role:mira",
        _host=host,
        _record_tick_log_finish=lambda ctx, **kwargs: None,
    )


class _Effect:
    def __init__(self, order: list[str], name: str) -> None:
        self._order = order
        self._name = name

    async def run(self) -> None:
        self._order.append(self._name)


def _reply_result(order: list[str]) -> TurnResult:
    return TurnResult(
        decision="reply",
        role_reply=RoleReply(content="在吗", mood="平静", thought="我想问一句"),
        reply_context=RoleReplyContext(moods=("平静",), previous_updated_at="stamp"),
        outbound=TurnOutbound(session_key="role:mira", content="在吗"),
        side_effects=[_Effect(order, "before")],
        success_side_effects=[_Effect(order, "success")],
        failure_side_effects=[_Effect(order, "failure")],
    )


def test_target_resolver_failure_propagates() -> None:
    def fail() -> tuple[str, str]:
        raise RuntimeError("binding unavailable")

    # Resolver errors surface to the tick boundary instead of becoming no_target.
    with pytest.raises(RuntimeError, match="binding unavailable"):
        _ = resolve_target_transport(fail)


def test_role_without_candidates_has_no_target() -> None:
    assert resolve_target_transport(lambda: None) is None


def test_incomplete_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        _ = resolve_target_transport(lambda: ("qq", ""))


def test_selected_target_is_returned_stripped() -> None:
    assert resolve_target_transport(lambda: (" qq ", " gqq:7 ")) == ("qq", "gqq:7")


@pytest.mark.asyncio
async def test_delivery_sends_once_to_the_tick_target() -> None:
    order: list[str] = []

    async def deliver(reply: InitiatedReply) -> InitiatedDelivery:
        order.append("deliver")
        assert (reply.channel, reply.chat_id, reply.content) == ("qq", "gqq:7", "在吗")
        assert reply.expected_mood_updated_at == "stamp"
        return InitiatedDelivery(message_ids=("m1",), complete=True)

    host = SimpleNamespace(deliver=AsyncMock(side_effect=deliver))
    await deliver_execute(
        _pipeline(host=host),
        AgentTickContext(
            session_key="role:mira", target_channel="qq", target_chat_id="gqq:7"
        ),
        ResolveResult(action="send", result=_reply_result(order)),
    )

    assert order == ["before", "deliver", "success"]


@pytest.mark.asyncio
async def test_skip_runs_its_effects_without_delivery() -> None:
    order: list[str] = []
    host = SimpleNamespace(deliver=AsyncMock())
    await deliver_execute(
        _pipeline(host=host),
        AgentTickContext(
            session_key="role:mira", target_channel="qq", target_chat_id="gqq:7"
        ),
        ResolveResult(
            action="skip",
            result=TurnResult(
                decision="skip",
                outbound=None,
                side_effects=[_Effect(order, "skip")],
            ),
        ),
    )
    assert order == ["skip"]
    host.deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_without_a_tick_target_fails() -> None:
    host = SimpleNamespace(deliver=AsyncMock())

    with pytest.raises(RuntimeError, match="unavailable"):
        await deliver_execute(
            _pipeline(host=host),
            AgentTickContext(session_key="role:mira"),
            ResolveResult(
                action="send", result=TurnResult(decision="skip", outbound=None)
            ),
        )
    host.deliver.assert_not_awaited()


_DISCARDED = "feed-mcp:c1"


def _sending_tick(*, sender, event_bus=None):
    """A tick that discards one feed item and then sends one message.

    Its success effects record the delivery key and ack the discarded item;
    its failure effects only ack the item. The real ``PROACTIVE_HOST`` and
    initiated delivery send it to the default bound private chat.
    """
    item = {
        "id": "c1",
        "ack_server": "feed-mcp",
        "url": "https://x.com",
        "title": "T",
        "source_name": "S",
        "published_at": "2026-01-01T00:00:00Z",
    }
    llm = FakeLLM(
        [
            ("get_content_events", {}),
            ("mark_not_interesting", {"item_ids": [_DISCARDED]}),
            (
                "message_push",
                {"message": "在吗", "mood": "平静", "thought": "我想问问"},
            ),
            ("finish_turn", {"decision": "reply"}),
        ]
    )
    state, acks = FakeStateStore(), FakeAckSink()
    tick = make_proactive_pipeline(
        llm_fn=llm,
        state_store=state,
        sender=sender,
        tool_deps=ToolDeps(ack_fn=acks, recent_chat_fn=AsyncMock(return_value=[])),
        gateway_deps=GatewayDeps(feed_fn=AsyncMock(return_value=[item])),
        event_bus=event_bus,
    )
    return tick, state, acks


@pytest.mark.asyncio
async def test_cancel_after_the_reply_is_stored_still_runs_success_effects() -> None:
    """Retiring the generation while the committed event goes out.

    The message was sent and stored: the delivery is recorded so it is not
    sent again, and the cancellation still stops the tick.
    """
    bus = EventBus()
    announcing, never = asyncio.Event(), asyncio.Event()

    async def slow_observer(_event: InitiatedMessageCommitted) -> None:
        announcing.set()
        await never.wait()

    bus.on(InitiatedMessageCommitted, slow_observer)
    sender = AsyncMock()
    sender.send.return_value = True
    tick, state, acks = _sending_tick(sender=sender, event_bus=bus)
    task = asyncio.create_task(tick.run())
    await announcing.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await bus.aclose()

    sender.send.assert_awaited_once()
    assert len(state._deliveries) == 1
    assert acks.all_keys() == {_DISCARDED}


@pytest.mark.asyncio
async def test_cancel_during_the_send_runs_neither_effect() -> None:
    """Retiring the generation mid-send: nothing was stored, nothing is settled."""
    sending, never = asyncio.Event(), asyncio.Event()

    async def send(_content: str) -> bool:
        sending.set()
        await never.wait()
        return True

    sender = AsyncMock()
    sender.send.side_effect = send
    tick, state, acks = _sending_tick(sender=sender)
    task = asyncio.create_task(tick.run())
    await sending.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert state._deliveries == []
    assert acks.calls == []
