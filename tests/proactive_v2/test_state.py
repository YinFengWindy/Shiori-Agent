from __future__ import annotations

import json
from pathlib import Path

from proactive_v2.state import ProactiveStateStore


def test_state_store_persists_structured_gate_diagnostics(
    tmp_path: Path,
):
    db_path = tmp_path / "proactive.db"

    store = ProactiveStateStore(db_path)
    store.record_tick_log_finish(
        tick_id="tick-1",
        session_key="role:mira",
        started_at="2026-08-10T10:03:49+00:00",
        finished_at="2026-08-10T10:03:50+00:00",
        gate_exit="loneliness",
        gate_name="relationship.loneliness",
        gate_reason="cooldown",
        gate_metadata={
            "loneliness_value": 100,
            "trigger_threshold": 60,
        },
        terminal_action=None,
        skip_reason="",
        steps_taken=0,
        alert_count=0,
        content_count=0,
        context_count=0,
        interesting_ids=[],
        discarded_ids=[],
        cited_ids=[],
        drift_entered=False,
        final_message="",
    )

    row = store._db.execute(
        "SELECT gate_exit, gate_name, gate_reason, gate_metadata FROM tick_log"
    ).fetchone()

    assert row is not None
    assert row["gate_exit"] == "loneliness"
    assert row["gate_name"] == "relationship.loneliness"
    assert row["gate_reason"] == "cooldown"
    assert json.loads(row["gate_metadata"]) == {
        "loneliness_value": 100,
        "trigger_threshold": 60,
    }
    store.close()
