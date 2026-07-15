from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.roles.scene_followup_runtime import SceneFollowupRuntime


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 14, hour, minute, tzinfo=timezone.utc)


def test_user_message_arms_first_followup_after_five_minutes(tmp_path: Path):
    runtime = SceneFollowupRuntime(tmp_path)
    session_key = "role:mira"

    state = runtime.handle_user_message(session_key, now=_utc(13, 39))

    assert state is not None
    assert state["attempt_index"] == 0
    assert datetime.fromisoformat(state["next_due_at"]) == _utc(13, 44)
    assert runtime.should_trigger(session_key, _utc(13, 43))[0] is False
    should_trigger, meta = runtime.should_trigger(session_key, _utc(13, 44))
    assert should_trigger is True
    assert meta["reason"] == "scene_followup_due"
    assert meta["attempt_index"] == 0


def test_successive_followups_accelerate_and_stop_after_third_send(tmp_path: Path):
    runtime = SceneFollowupRuntime(tmp_path)
    session_key = "role:mira"
    runtime.handle_user_message(session_key, now=_utc(13, 39))

    second = runtime.handle_followup_sent(session_key, now=_utc(13, 44))
    assert second is not None
    assert second["attempt_index"] == 1
    assert datetime.fromisoformat(second["next_due_at"]) == _utc(13, 47)

    third = runtime.handle_followup_sent(session_key, now=_utc(13, 47))
    assert third is not None
    assert third["attempt_index"] == 2
    assert datetime.fromisoformat(third["next_due_at"]) == _utc(13, 48)

    closed = runtime.handle_followup_sent(session_key, now=_utc(13, 48))
    assert closed is None
    assert runtime.read(session_key) is None


def test_new_user_message_resets_followup_chain_from_latest_interaction(tmp_path: Path):
    runtime = SceneFollowupRuntime(tmp_path)
    session_key = "role:mira"
    runtime.handle_user_message(session_key, now=_utc(13, 39))
    runtime.handle_followup_sent(session_key, now=_utc(13, 44))

    reset = runtime.handle_user_message(session_key, now=_utc(13, 45))

    assert reset is not None
    assert reset["attempt_index"] == 0
    assert datetime.fromisoformat(reset["next_due_at"]) == _utc(13, 50)


def test_stale_scene_expires_instead_of_catching_up_after_restart(tmp_path: Path):
    runtime = SceneFollowupRuntime(tmp_path)
    session_key = "role:mira"
    runtime.handle_user_message(session_key, now=_utc(13, 39))

    should_trigger, meta = runtime.should_trigger(
        session_key,
        _utc(13, 39) + timedelta(hours=10),
    )

    assert should_trigger is False
    assert meta["reason"] == "expired"
    assert runtime.read(session_key) is None


def test_scene_change_closes_pending_followups(tmp_path: Path):
    runtime = SceneFollowupRuntime(tmp_path)
    session_key = "role:mira"
    runtime.handle_user_message(session_key, now=_utc(13, 39))

    runtime.close(session_key)

    assert runtime.should_trigger(session_key, _utc(13, 44)) == (
        False,
        {"reason": "no_scene"},
    )


def test_shared_scene_decision_updates_key_and_closes_on_transition(
    tmp_path: Path,
):
    runtime = SceneFollowupRuntime(tmp_path)
    session_key = "role:mira"
    runtime.handle_user_message(session_key, now=_utc(13, 39))

    state = runtime.apply_scene_decision(
        session_key,
        "same",
        "night-run",
        now=_utc(13, 40),
    )

    assert state is not None
    assert state["scene_key"] == "night-run"
    runtime.apply_scene_decision(session_key, "closed", now=_utc(13, 41))
    assert runtime.read(session_key) is None
