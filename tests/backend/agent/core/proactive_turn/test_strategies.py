"""Core motives preserve priority and never deny another motive's admission."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from agent.core.proactive_turn.gates import (
    ProactiveGateChain,
    ProactiveGateContext,
    ProactiveGateCompletion,
    ProactiveMode,
)
from agent.core.proactive_turn.strategies import (
    SceneFollowupStrategy,
    RelationshipStrategy,
)


def _context():
    return ProactiveGateContext(
        "tick", "role:mira", datetime.now(timezone.utc), ("desktop", "role:mira")
    )


@pytest.mark.parametrize("outcome", ["delivered", "closed"])
def test_scene_claims_before_relationship_and_finalizes_exact_outcome(outcome):
    runtime = MagicMock()
    runtime.should_trigger_scene_followup.return_value = (True, {"attempt_index": 1})
    chain = ProactiveGateChain(
        motives=[RelationshipStrategy(runtime), SceneFollowupStrategy(runtime)]
    )
    result = chain.evaluate(_context())
    assert result.activation is not None
    assert result.activation.mode == ProactiveMode.SCENE_FOLLOWUP
    runtime.should_trigger_proactive.assert_not_called()
    chain.finalize(
        ProactiveGateCompletion(
            result.activation, "role:mira", _context().now_utc, outcome
        )
    )
    assert runtime.handle_scene_followup_sent.call_count == int(outcome == "delivered")
    assert runtime.close_scene_followup.call_count == int(outcome == "closed")


@pytest.mark.parametrize("reason", ["cooldown", "below_threshold", "no_snapshot"])
def test_missing_relationship_preserves_diagnostics_and_does_not_block(reason):
    runtime = MagicMock()
    runtime.should_trigger_scene_followup.return_value = (False, {"reason": "not_due"})
    runtime.should_trigger_proactive.return_value = (
        False,
        {"reason": reason, "loneliness_value": 20},
    )
    result = ProactiveGateChain(
        motives=[SceneFollowupStrategy(runtime), RelationshipStrategy(runtime)]
    ).evaluate(_context())
    assert not result.blocked
    assert result.activation is None
    assert result.trace[0].reason == "not_due"
    assert result.trace[1].metadata == {"reason": reason, "loneliness_value": 20}
