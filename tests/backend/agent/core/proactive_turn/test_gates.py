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
        lambda: [
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
            lambda: [
                _Gate("same", 0, ProactiveGateDecision.continue_(), calls),
                _Gate("same", 1, ProactiveGateDecision.continue_(), calls),
            ]
        )


def test_gate_chain_preserves_block_metadata():
    calls: list[str] = []
    chain = ProactiveGateChain(
        lambda: [
            _Gate(
                "relationship.loneliness",
                0,
                ProactiveGateDecision.block(
                    "cooldown",
                    metadata={"cooldown_until": "2026-08-10T18:16:40+08:00"},
                ),
                calls,
            )
        ]
    )

    result = chain.evaluate(_ctx())

    assert result.blocked is True
    assert result.blocked_gate_name == "relationship.loneliness"
    assert result.reason == "cooldown"
    assert result.trace[0].metadata == {"cooldown_until": "2026-08-10T18:16:40+08:00"}


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
        ProactiveGateChain(lambda: [_Broken()]).evaluate(_ctx())


def test_gate_chain_rejects_unknown_decision_kind():
    calls: list[str] = []
    invalid = ProactiveGateDecision(kind="unknown")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="unknown decision"):
        ProactiveGateChain(lambda: [_Gate("invalid", 0, invalid, calls)]).evaluate(
            _ctx()
        )


def test_global_denial_precedes_higher_priority_core_motive():
    calls: list[str] = []
    chain = ProactiveGateChain(
        lambda: [_Gate("global", -100, ProactiveGateDecision.block("busy"), calls)],
        motives=[
            _Gate(
                "scene",
                100,
                ProactiveGateDecision.activate(
                    ProactiveMode.SCENE_FOLLOWUP, reason="due"
                ),
                calls,
            )
        ],
    )
    result = chain.evaluate(_ctx())
    assert result.blocked
    assert result.reason == "busy"
    assert calls == ["global"]


def test_core_motive_cannot_veto_global_admission():
    chain = ProactiveGateChain(
        motives=[_Gate("relationship", 0, ProactiveGateDecision.block("cooldown"), [])]
    )
    with pytest.raises(ValueError, match="cannot block global admission"):
        chain.evaluate(_ctx())


def test_gate_chain_reads_current_gates_on_every_evaluation():
    """A removed plugin gate stops applying and an added one applies (#855)."""
    calls: list[str] = []
    blocker = _Gate("plugin.blocker", 0, ProactiveGateDecision.block("busy"), calls)
    active: list[ProactiveGateAdapter] = [blocker]
    chain = ProactiveGateChain(lambda: active)

    assert chain.evaluate(_ctx()).blocked
    active.clear()
    assert not chain.evaluate(_ctx()).blocked
    active.append(blocker)
    assert chain.evaluate(_ctx()).blocked
    assert calls == ["plugin.blocker", "plugin.blocker"]
    # Names are re-validated only when the gate set changes.
    active.append(_Gate("plugin.blocker", 1, ProactiveGateDecision.continue_(), []))
    with pytest.raises(ValueError, match="Duplicate proactive gate name"):
        chain.evaluate(_ctx())


def test_gate_removed_after_activation_still_finalizes_on_original_gate():
    """Completion reaches the claiming gate even after its removal (#855)."""

    class _Claiming(ProactiveGateAdapter):
        name = "plugin.claim"

        def __init__(self) -> None:
            self.completions: list[ProactiveGateCompletion] = []

        def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
            return ProactiveGateDecision.activate(
                ProactiveMode.SCENE_FOLLOWUP, reason="due"
            )

        def finalize(self, completion: ProactiveGateCompletion) -> None:
            self.completions.append(completion)

    gate = _Claiming()
    active: list[ProactiveGateAdapter] = [gate]
    chain = ProactiveGateChain(lambda: active)
    activation = chain.evaluate(_ctx()).activation
    assert activation is not None
    active.clear()

    completion = ProactiveGateCompletion(
        activation, "role:mira", datetime.now(timezone.utc), "delivered"
    )
    chain.finalize(completion)

    assert gate.completions == [completion]
