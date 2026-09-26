"""Published account state ignores candidate generations and stale reporters."""

from __future__ import annotations

import pytest

from core.accounts.models import AccountRecord
from core.accounts.runtime_state import AccountRuntimeState


def test_candidate_report_is_hidden_until_publication():
    state = AccountRuntimeState()
    row = AccountRecord("id", "plugin", "platform", "101", "config", role_id="role")
    state.set_plugin_enabled("plugin", True, "direct")
    state.register(row.id, "old", "direct")
    state.report(row.id, "old", "direct", "online", frozenset({"contacts"}), "")
    access = state.authorize(row, "role")

    state.set_plugin_enabled("plugin", False, "candidate")
    state.register(row.id, "new", "candidate")
    assert state.snapshot(row).connection == "online"
    assert state.validate_access(row, access)
    state.drop("candidate")
    assert state.snapshot(row).connection == "online"

    state.register(row.id, "replacement", "next")
    state.publish("next")
    assert state.snapshot(row).connection == "unknown"
    assert not state.validate_access(row, access)


def test_old_reporter_cannot_reclaim_same_generation():
    state = AccountRuntimeState()
    state.register("id", "old", "direct")
    state.unregister("id", "old", "direct")
    state.register("id", "new", "direct")
    with pytest.raises(RuntimeError, match="superseded"):
        state.ensure_registration_allowed("id", "old", "direct")
    with pytest.raises(RuntimeError, match="no longer active"):
        state.report("id", "old", "direct", "online", frozenset(), "")
