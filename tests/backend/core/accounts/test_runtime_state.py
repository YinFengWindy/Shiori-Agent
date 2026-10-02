"""Published account state ignores candidate generations and stale reporters."""

from __future__ import annotations

import pytest

from shiori_sdk.accounts.models import AccountRecord
from core.accounts.runtime_state import AccountRuntimeState


def test_candidate_report_is_hidden_until_publication():
    state = AccountRuntimeState()
    row = AccountRecord("p:101", "p", "platform", "101", "config", role_id="role")
    state.register(row, "old", "direct")
    state.report(row.id, "old", "direct", "online", frozenset({"contacts"}), "")
    access = state.authorize(row, "role")

    state.register(row, "new", "candidate")
    assert state.snapshot(row).connection == "online"
    assert state.validate_access(access)
    state.drop("candidate")
    assert state.snapshot(row).connection == "online"

    state.register(row, "replacement", "next")
    state.publish("next")
    assert state.snapshot(row).connection == "unknown"
    assert not state.validate_access(access)


def test_old_reporter_cannot_reclaim_same_generation():
    state = AccountRuntimeState()
    row = AccountRecord("p:101", "p", "platform", "101", "config", role_id="role")
    state.register(row, "old", "direct")
    state.unregister(row.id, "old", "direct")
    state.register(row, "new", "direct")
    with pytest.raises(RuntimeError, match="superseded"):
        state.ensure_registration_allowed(row.id, "old", "direct")
    with pytest.raises(RuntimeError, match="no longer active"):
        state.report(row.id, "old", "direct", "online", frozenset(), "")
    # Releasing the superseded instance leaves the replacement indexed.
    state.release(row.id, "old", "direct")
    assert state.published.records == {row.id: row}
