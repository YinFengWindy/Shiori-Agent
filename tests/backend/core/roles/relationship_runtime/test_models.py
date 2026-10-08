from core.roles.relationship_runtime.models import (
    _normalize_behavior_profile,
    _normalize_relation_state,
)


def test_relation_state_preserves_legitimate_zero_and_defaults_missing() -> None:
    state = _normalize_relation_state({"closeness": 0, "security": None})

    assert state["closeness"] == 0.0
    assert state["security"] == 0.5


def test_behavior_profile_preserves_legitimate_zero() -> None:
    profile = _normalize_behavior_profile(
        {"trigger_threshold": 0, "night_suppression": 0.0}
    )

    assert profile["trigger_threshold"] == 0.0
    assert profile["night_suppression"] == 0.0
