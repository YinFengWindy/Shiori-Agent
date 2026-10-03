"""Invalidation replaces derived state without publishing changes to old readers."""

from session.maintenance_progress import MaintenanceProgress
import json


def test_invalidation_discards_every_derived_artifact_without_mutating_previous_state():
    previous = MaintenanceProgress(
        ownership="old owner",
        legacy_cuts={"user": 2},
        windows={"user": 4},
        window_versions={"user": 3},
        summaries={"user": "working state"},
        summary_source_ids={"user": ["message"]},
        generation=2,
        memory_version=7,
        recent_context_version=5,
        recent_context_source_ids=["message"],
        published_version=7,
        relationship_version=6,
        pending_consumers={"source_ref": "message"},
        consumer_error="unavailable",
    )
    snapshot = previous.dump()
    invalidated = previous.invalidated()
    assert previous.dump() == snapshot
    assert invalidated.ownership == "old owner"
    assert invalidated.generation == 3 and invalidated.memory_version == 8
    assert (
        not invalidated.legacy_cuts
        and not invalidated.windows
        and not invalidated.window_versions
        and not invalidated.summaries
        and not invalidated.summary_source_ids
    )
    assert (
        invalidated.recent_context_version
        == invalidated.published_version
        == invalidated.relationship_version
        == 0
    )
    assert not invalidated.recent_context_source_ids
    assert not invalidated.pending_consumers and not invalidated.consumer_error


def test_rebinding_away_and_back_never_revives_an_unscoped_session_window():
    unbound = MaintenanceProgress(
        windows={"session": 4},
        summaries={"session": "state"},
        summary_source_ids={"session": ["message"]},
    )
    restored = unbound.rebound('["thread:mira:desktop"]').rebound("")
    assert restored.windows["session"] == 0
    assert not restored.summaries and not restored.summary_source_ids


def test_additive_binding_preserves_user_window_but_rebinding_invalidates_it():
    desktop, private = "thread:mira:desktop", "thread:mira:qq:902"
    previous = MaintenanceProgress(
        ownership=json.dumps([desktop]),
        windows={"user": 40},
        summaries={"user": "desktop working state"},
        summary_source_ids={"user": ["desktop-message"]},
        memory_version=7,
    )
    ownership = {desktop: "", private: "2026-01-01T00:00:00+00:00"}
    added = previous.rebound(json.dumps(ownership))
    assert added.windows["user"] == 40
    assert added.summaries == previous.summaries
    assert added.summary_source_ids == previous.summary_source_ids
    assert added.memory_version == 7 and added.generation == 1
    rebound = added.rebound(
        json.dumps({**ownership, private: "2026-01-02T00:00:00+00:00"})
    )
    assert rebound.windows["user"] == 0 and not rebound.summaries
    removed = added.rebound(json.dumps([desktop]))
    assert removed.windows["user"] == 0 and not removed.summaries
