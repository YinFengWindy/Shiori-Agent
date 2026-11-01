"""Strategy-trace envelopes written beside a role's memory directory."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

StrategyTraceType = Literal[
    "route", "proactive_stage", "proactive_config", "proactive_rate", "spawn"
]
StrategyTraceSubjectKind = Literal["session", "job", "action", "role", "global"]


@dataclass(frozen=True)
class StrategyTraceSubject:
    kind: StrategyTraceSubjectKind
    id: str


@dataclass(frozen=True)
class StrategyTraceEnvelope:
    trace_type: StrategyTraceType
    source: str
    subject: StrategyTraceSubject
    timestamp: str
    payload: dict[str, Any]


def build_strategy_trace_envelope(
    *,
    trace_type: StrategyTraceType,
    source: str,
    subject_kind: StrategyTraceSubjectKind,
    subject_id: str,
    payload: dict[str, Any],
    timestamp: str | None = None,
) -> dict[str, Any]:
    """The JSON object one trace line stores around ``payload``."""
    envelope = StrategyTraceEnvelope(
        trace_type=trace_type,
        source=source,
        subject=StrategyTraceSubject(kind=subject_kind, id=subject_id),
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        payload=payload,
    )
    return {
        "trace_type": envelope.trace_type,
        "source": envelope.source,
        "subject": asdict(envelope.subject),
        "ts": envelope.timestamp,
        "payload": envelope.payload,
    }


def config_snapshot_payload(cfg: Any) -> dict[str, Any]:
    """The loop config fields worth a trace line when the pipeline is (re)built."""
    return {
        "enabled": cfg.enabled,
        "score_llm_threshold": cfg.score_llm_threshold,
        "tick_interval_s0": cfg.tick_interval_s0,
        "tick_interval_s1": cfg.tick_interval_s1,
        "tick_jitter": cfg.tick_jitter,
        "memory_history_gate_enabled": cfg.memory_history_gate_enabled,
        "sleep_modifier_sleeping": cfg.sleep_modifier_sleeping,
    }


def rate_decision_payload(
    cfg: Any, *, base_score: float | None, interval: int, mode: str
) -> dict[str, Any]:
    """One next-tick interval decision and the config it came from."""
    return {
        "mode": mode,
        "base_score": round(base_score, 4) if base_score is not None else None,
        "interval_seconds": int(interval),
        "score_llm_threshold": cfg.score_llm_threshold,
        "tick_interval_s0": cfg.tick_interval_s0,
        "tick_interval_s1": cfg.tick_interval_s1,
        "tick_jitter": cfg.tick_jitter,
    }


def append_loop_trace(
    workspace: Path, filename: str, payload: dict[str, Any], *, role_id: str
) -> None:
    """Appends ``payload`` to ``memory/<filename>``; a failed write only warns."""
    try:
        memory_dir = workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        if "trace_type" not in payload or "payload" not in payload:
            trace_type: StrategyTraceType = (
                "proactive_config" if "config" in filename else "proactive_rate"
            )
            source = (
                "proactive.config"
                if trace_type == "proactive_config"
                else "proactive.rate"
            )
            payload = {
                **build_strategy_trace_envelope(
                    trace_type=trace_type,
                    source=source,
                    subject_kind="role" if role_id else "global",
                    subject_id=role_id or filename.removesuffix(".jsonl"),
                    payload=payload,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                **payload,
            }
        with (memory_dir / filename).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[proactive] write trace failed %s: %s", filename, exc)
