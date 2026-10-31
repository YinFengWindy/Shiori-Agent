from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.core.proactive_turn import ResolveResult
from agent.core.proactive_turn.delivery import (
    deliver_execute,
    resolve_target_transport,
)
from agent.turns.result import TurnOutbound, TurnResult
from core.roles.reply_state import RoleReply, RoleReplyContext
from proactive_v2.context import AgentTickContext
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply


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

    host = SimpleNamespace(
        natural_reply_active=lambda: False,
        deliver=AsyncMock(side_effect=deliver),
        commit_natural_reply=AsyncMock(),
    )
    await deliver_execute(
        _pipeline(host=host),
        AgentTickContext(
            session_key="role:mira", target_channel="qq", target_chat_id="gqq:7"
        ),
        ResolveResult(action="send", result=_reply_result(order)),
    )

    assert order == ["before", "deliver", "success"]
    host.commit_natural_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_runs_its_effects_without_delivery() -> None:
    order: list[str] = []
    host = SimpleNamespace(
        deliver=AsyncMock(),
        commit_natural_reply=AsyncMock(),
        natural_reply_active=lambda: False,
    )
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
    host = SimpleNamespace(deliver=AsyncMock(), natural_reply_active=lambda: False)

    with pytest.raises(RuntimeError, match="unavailable"):
        await deliver_execute(
            _pipeline(host=host),
            AgentTickContext(session_key="role:mira"),
            ResolveResult(
                action="send", result=TurnResult(decision="skip", outbound=None)
            ),
        )
    host.deliver.assert_not_awaited()
