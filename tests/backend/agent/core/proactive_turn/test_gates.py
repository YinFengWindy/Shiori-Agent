from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.core.proactive_turn.gates import (
    ProactiveGateAdapter,
    ProactiveGateChain,
    ProactiveGateCompletion,
    ProactiveGateContext,
    ProactiveGateDecision,
    ProactiveGateActivation,
    ProactiveMode,
    resolve_gate_attempt_index,
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
        target_transport=("desktop", "role:mira"),
    )


def test_gate_chain_orders_by_priority_and_stops_after_activation():
    calls: list[str] = []
    chain = ProactiveGateChain(
        motives=[
            _Gate("low", 0, ProactiveGateDecision.continue_(), calls),
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
    assert result.activation is not None
    assert result.activation.mode == ProactiveMode.SCENE_FOLLOWUP


def test_gate_chain_rejects_duplicate_names():
    calls: list[str] = []
    with pytest.raises(ValueError, match="Duplicate proactive gate name"):
        ProactiveGateChain(
            motives=[
                _Gate("same", 0, ProactiveGateDecision.continue_(), calls),
                _Gate("same", 1, ProactiveGateDecision.continue_(), calls),
            ]
        )


def test_resolve_gate_attempt_index_accepts_non_negative_integer_strings():
    gate = ProactiveGateActivation(
        gate_name="scene",
        mode=ProactiveMode.SCENE_FOLLOWUP,
        reason="due",
        metadata={"attempt_index": "2"},
        gate=ProactiveGateAdapter(),
    )

    assert resolve_gate_attempt_index(gate) == 2


@pytest.mark.parametrize("value", [True, -1, "invalid", object()])
def test_resolve_gate_attempt_index_rejects_invalid_metadata(value):
    gate = ProactiveGateActivation(
        gate_name="scene",
        mode=ProactiveMode.SCENE_FOLLOWUP,
        reason="due",
        metadata={"attempt_index": value},
        gate=ProactiveGateAdapter(),
    )

    with pytest.raises(ValueError, match="attempt_index"):
        resolve_gate_attempt_index(gate)


def test_gate_chain_propagates_gate_errors():
    class _Broken(ProactiveGateAdapter):
        name = "broken"
        priority = 0

        def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        ProactiveGateChain(motives=[_Broken()]).evaluate(_ctx())


def test_gate_chain_rejects_unknown_decision_kind():
    calls: list[str] = []
    invalid = ProactiveGateDecision(kind="unknown")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="unknown decision"):
        ProactiveGateChain(motives=[_Gate("invalid", 0, invalid, calls)]).evaluate(
            _ctx()
        )


def test_core_motive_cannot_veto_global_admission():
    chain = ProactiveGateChain(
        motives=[
            _Gate(
                "relationship",
                0,
                ProactiveGateDecision(kind="block", reason="cooldown"),
                [],
            )
        ]
    )
    with pytest.raises(ValueError, match="cannot block global admission"):
        chain.evaluate(_ctx())


def test_completion_reaches_the_motive_that_claimed_the_tick():
    class _Claiming(ProactiveGateAdapter):
        name = "scene"

        def __init__(self) -> None:
            self.completions: list[ProactiveGateCompletion] = []

        def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
            return ProactiveGateDecision.activate(
                ProactiveMode.SCENE_FOLLOWUP, reason="due"
            )

        def finalize(self, completion: ProactiveGateCompletion) -> None:
            self.completions.append(completion)

    gate = _Claiming()
    chain = ProactiveGateChain(motives=[gate])
    activation = chain.evaluate(_ctx()).activation
    assert activation is not None

    completion = ProactiveGateCompletion(
        activation, "role:mira", datetime.now(timezone.utc), "delivered"
    )
    chain.finalize(completion)

    assert gate.completions == [completion]
