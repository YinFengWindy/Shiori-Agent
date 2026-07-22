from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.core.proactive_turn.gates import (
    ProactiveGateAdapter,
    ProactiveGateChain,
    ProactiveGateContext,
    ProactiveGateDecision,
    ProactiveMode,
)


class _Gate(ProactiveGateAdapter):
    def __init__(self, name: str, priority: int, decision, calls: list[str]) -> None:
        self.name = name
        self.priority = priority
        self._decision = decision
        self._calls = calls

    def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
        self._calls.append(self.name)
        return self._decision


def _ctx() -> ProactiveGateContext:
    return ProactiveGateContext(
        tick_id="tick",
        session_key="role:mira",
        now_utc=datetime.now(timezone.utc),
        target_transports=(("desktop", "role:mira"),),
    )


def test_gate_chain_orders_by_priority_and_stops_after_activation():
    calls: list[str] = []
    chain = ProactiveGateChain(
        [
            _Gate("low", 0, ProactiveGateDecision.block("low"), calls),
            _Gate(
                "high",
                100,
                ProactiveGateDecision.activate(
                    ProactiveMode.SCENE_FOLLOWUP,
                    reason="due",
                ),
                calls,
            ),
        ]
    )

    result = chain.evaluate(_ctx())

    assert calls == ["high"]
    assert result.blocked is False
    assert result.activation is not None
    assert result.activation.mode == ProactiveMode.SCENE_FOLLOWUP


def test_gate_chain_rejects_duplicate_names():
    calls: list[str] = []
    with pytest.raises(ValueError, match="Duplicate proactive gate name"):
        ProactiveGateChain(
            [
                _Gate("same", 0, ProactiveGateDecision.continue_(), calls),
                _Gate("same", 1, ProactiveGateDecision.continue_(), calls),
            ]
        )


def test_gate_chain_propagates_gate_errors():
    class _Broken(ProactiveGateAdapter):
        name = "broken"
        priority = 0

        def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        ProactiveGateChain([_Broken()]).evaluate(_ctx())


def test_gate_chain_rejects_unknown_decision_kind():
    calls: list[str] = []
    invalid = ProactiveGateDecision(kind="unknown")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="unknown decision"):
        ProactiveGateChain([_Gate("invalid", 0, invalid, calls)]).evaluate(_ctx())
