"""Invalidation replaces derived state without publishing changes to old readers."""

import pytest

from session.maintenance_progress import MaintenanceProgress


@pytest.mark.parametrize("ownership", [None, "new owner"])
def test_invalidation_discards_every_derived_artifact_without_mutating_previous_state(
    ownership,
):
    previous = MaintenanceProgress(
        ownership="old owner",
        legacy_cuts={"user": 2},
        windows={"user": 4},
        window_versions={"user": 3},
        summaries={"user": "working state"},
        summary_source_ids={"user": ["message"]},
        request_owners={"user": "connection:model"},
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
    invalidated = previous.invalidated(ownership=ownership)
    assert previous.dump() == snapshot
    assert invalidated.ownership == ("old owner" if ownership is None else ownership)
    assert invalidated.generation == 3 and invalidated.memory_version == 8
    assert (
        not invalidated.legacy_cuts
        and not invalidated.windows
        and not invalidated.window_versions
        and not invalidated.summaries
        and not invalidated.summary_source_ids
        and not invalidated.request_owners
    )
    assert (
        invalidated.recent_context_version
        == invalidated.published_version
        == invalidated.relationship_version
        == 0
    )
    assert not invalidated.recent_context_source_ids
    assert not invalidated.pending_consumers and not invalidated.consumer_error
