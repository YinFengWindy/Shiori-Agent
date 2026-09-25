from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.core.proactive_turn import ResolveResult
from agent.core.proactive_turn.delivery import (
    deliver_execute,
    resolve_target_transport,
)
from agent.turns.result import TurnResult
from proactive_v2.context import AgentTickContext


def _pipeline(*, target_transport_fn=None, orchestrator=None):
    return SimpleNamespace(
        _session_key="role:mira",
        _turn_orchestrator=orchestrator,
        _target_transport_fn=target_transport_fn,
        _record_tick_log_finish=lambda ctx, **kwargs: None,
    )


def test_target_resolver_failure_propagates() -> None:
    def fail() -> tuple[str, str]:
        raise RuntimeError("binding unavailable")

    # Resolver errors surface to the tick boundary instead of becoming no_target.
    with pytest.raises(RuntimeError, match="binding unavailable"):
        _ = resolve_target_transport(_pipeline(target_transport_fn=fail))


def test_role_without_candidates_has_no_target() -> None:
    assert resolve_target_transport(_pipeline(target_transport_fn=lambda: None)) is None


def test_incomplete_target_is_rejected() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        _ = resolve_target_transport(_pipeline(target_transport_fn=lambda: ("qq", "")))


def test_selected_target_is_returned_stripped() -> None:
    pipeline = _pipeline(target_transport_fn=lambda: (" qq ", " gqq:7 "))

    assert resolve_target_transport(pipeline) == ("qq", "gqq:7")


@pytest.mark.asyncio
async def test_delivery_sends_once_to_the_tick_target() -> None:
    orchestrator = SimpleNamespace(handle_proactive_turn=AsyncMock(return_value=True))
    ctx = AgentTickContext(
        session_key="role:mira", target_channel="qq", target_chat_id="gqq:7"
    )
    result = TurnResult(decision="skip", outbound=None)

    await deliver_execute(
        _pipeline(orchestrator=orchestrator),
        ctx,
        ResolveResult(action="send", result=result),
    )

    orchestrator.handle_proactive_turn.assert_awaited_once_with(
        result=result, session_key="role:mira", channel="qq", chat_id="gqq:7"
    )


@pytest.mark.asyncio
async def test_delivery_without_a_tick_target_fails() -> None:
    orchestrator = SimpleNamespace(handle_proactive_turn=AsyncMock(return_value=True))

    with pytest.raises(RuntimeError, match="unavailable"):
        await deliver_execute(
            _pipeline(orchestrator=orchestrator),
            AgentTickContext(session_key="role:mira"),
            ResolveResult(
                action="send", result=TurnResult(decision="skip", outbound=None)
            ),
        )
    orchestrator.handle_proactive_turn.assert_not_awaited()
