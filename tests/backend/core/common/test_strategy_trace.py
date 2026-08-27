from __future__ import annotations

from typing import get_args

from core.common.strategy_trace import (
    StrategyTraceSubjectKind,
    build_strategy_trace_envelope,
)


def test_build_strategy_trace_envelope_uses_subject_scope():
    payload = build_strategy_trace_envelope(
        trace_type="spawn",
        source="agent.spawn",
        subject_kind="job",
        subject_id="abcd1234",
        payload={"status": "completed"},
        timestamp="2026-03-09T00:00:00+00:00",
    )

    assert payload["trace_type"] == "spawn"
    assert payload["source"] == "agent.spawn"
    assert payload["subject"] == {"kind": "job", "id": "abcd1234"}
    assert payload["payload"] == {"status": "completed"}


def test_strategy_trace_subject_kind_accepts_role():
    assert "role" in get_args(StrategyTraceSubjectKind)

    payload = build_strategy_trace_envelope(
        trace_type="proactive_rate",
        source="proactive.rate",
        subject_kind="role",
        subject_id="mira",
        payload={"mode": "adaptive"},
    )

    assert payload["subject"] == {"kind": "role", "id": "mira"}
