from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from proactive_v2.loop import ProactiveLoop


class _ProactiveTraceLoop(ProactiveLoop):
    def __init__(self, workspace: Path, *, role_id: str = "") -> None:
        self._sessions = SimpleNamespace(workspace=workspace)
        self._cfg = SimpleNamespace(
            enabled=True,
            default_role_id=role_id,
            score_llm_threshold=0.6,
            tick_interval_s0=30,
            tick_interval_s1=60,
            tick_jitter=0.1,
            anyaction_enabled=True,
            anyaction_min_interval_seconds=60,
            anyaction_probability_min=0.1,
            anyaction_probability_max=0.5,
            memory_history_gate_enabled=True,
        )


def test_proactive_trace_uses_global_subject_without_role(tmp_path: Path):
    loop = _ProactiveTraceLoop(tmp_path)
    loop._trace_proactive_rate_decision(base_score=0.5, interval=60, mode="adaptive")

    trace_path = tmp_path / "memory" / "proactive_rate_trace.jsonl"
    line = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert line["trace_type"] == "proactive_rate"
    assert line["subject"] == {"kind": "global", "id": "proactive_rate_trace"}
    assert line["payload"]["mode"] == "adaptive"


def test_proactive_trace_uses_role_subject_when_configured(tmp_path: Path):
    loop = _ProactiveTraceLoop(tmp_path, role_id="mira")
    loop._trace_proactive_rate_decision(base_score=0.5, interval=60, mode="adaptive")

    trace_path = tmp_path / "memory" / "proactive_rate_trace.jsonl"
    line = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert line["subject"] == {"kind": "role", "id": "mira"}
