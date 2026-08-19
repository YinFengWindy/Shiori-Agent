"""Phase 1+2: insert haystack messages into SessionStore, then consolidate."""

from __future__ import annotations

import logging
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from core.memory.engine import MemoryIngestRequest, MemoryScope

from .dataset import LMEInstance
from .runtime import BenchmarkRuntime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestFailure:
    """A recoverable per-pair memory-ingest failure in a benchmark run."""

    pair_index: int
    source_ref: str
    error: str


@dataclass(frozen=True)
class IngestTurnResult:
    """Outcome of replaying one LongMemEval dialogue session."""

    accepted_pairs: int = 0
    rejected_pairs: int = 0
    failures: tuple[IngestFailure, ...] = ()


def _parse_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return datetime.now(tz=timezone.utc).isoformat()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return raw


def _ingest_state_path(rt: BenchmarkRuntime, question_id: str) -> Path:
    return rt.workspace / "ingest_state.json"


def _load_ingest_state(rt: BenchmarkRuntime, question_id: str) -> dict | None:
    path = _ingest_state_path(rt, question_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to load ingest state: %s", path)
        return None


def _write_ingest_state(
    rt: BenchmarkRuntime,
    question_id: str,
    *,
    completed: bool,
    expected_turns: int,
    ingested_turns: int,
    accepted_pairs: int,
    rejected_pairs: int,
    failures: list[IngestFailure],
) -> None:
    _ingest_state_path(rt, question_id).write_text(
        json.dumps(
            {
                "question_id": question_id,
                "completed": completed,
                "expected_turns": expected_turns,
                "ingested_turns": ingested_turns,
                "accepted_pairs": accepted_pairs,
                "rejected_pairs": rejected_pairs,
                "failed_pairs": len(failures),
                "failures": [asdict(failure) for failure in failures],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _is_ingested(rt: BenchmarkRuntime, question_id: str) -> bool:
    state = _load_ingest_state(rt, question_id)
    return bool(state and state.get("completed") is True)


async def _ingest_turns(
    rt: BenchmarkRuntime,
    session_key: str,
    session_index: int,
    turns,
) -> IngestTurnResult:
    """Write conversation turns into the memory engine (pair-wise ingest).

    The default_memory engine consumes one (user, assistant) pair per
    ingest call via its post_response_worker; LongMemEval history is a
    flat dialogue, so we chunk it into pairs and ingest each one.
    """
    engine = rt.core.memory_runtime.engine
    scope = MemoryScope(
        role_id="benchmark",
        session_key=session_key,
        channel="benchmark",
    )

    pairs: list[list[dict]] = []
    for turn in turns:
        if isinstance(turn, dict):
            role = str(turn.get("role", "") or "")
            content = str(turn.get("content", "") or "")
        else:
            role = str(getattr(turn, "role", "") or "")
            content = str(getattr(turn, "content", "") or "")
        if role == "user" and content:
            pairs.append([{"role": "user", "content": content}])
        elif role == "assistant" and content and pairs:
            pairs[-1].append({"role": "assistant", "content": content})

    accepted_pairs = 0
    rejected_pairs = 0
    failures: list[IngestFailure] = []
    for i, pair in enumerate(pairs):
        source_ref = f"{session_key}#ingest:{session_index}:{i}"
        request = MemoryIngestRequest(
            content=pair,
            source_kind="conversation_turn",
            scope=scope,
            metadata={"source_ref": source_ref},
        )
        try:
            result = await engine.ingest(request)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "memory ingest failed: session=%s pair=%d source_ref=%s error=%s",
                session_key,
                i,
                source_ref,
                error,
            )
            failures.append(
                IngestFailure(pair_index=i, source_ref=source_ref, error=error)
            )
            continue
        if result.accepted:
            accepted_pairs += 1
        else:
            rejected_pairs += 1
            logger.warning(
                "memory ingest rejected: session=%s pair=%d source_ref=%s summary=%s",
                session_key,
                i,
                source_ref,
                result.summary,
            )
    return IngestTurnResult(
        accepted_pairs=accepted_pairs,
        rejected_pairs=rejected_pairs,
        failures=tuple(failures),
    )


async def ingest_instance(
    rt: BenchmarkRuntime,
    instance: LMEInstance,
    *,
    force: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> int:
    """Insert all haystack sessions and run consolidation per session boundary.

    Returns total turn count. Calls on_progress(done, total) after each session.
    """
    session_key = instance.session_key
    sm = rt.core.session_manager

    expected_turns = sum(len(turns) for turns in instance.haystack_sessions)
    if not force and _is_ingested(rt, instance.question_id):
        logger.info("skip ingest (already done): %s", session_key)
        return 0

    dates = instance.haystack_dates
    sessions = instance.haystack_sessions

    if not sessions:
        logger.warning("instance %s has no haystack sessions", instance.question_id)
        return 0

    while len(dates) < len(sessions):
        dates.append("")

    total_turns = 0
    accepted_pairs = 0
    rejected_pairs = 0
    failures: list[IngestFailure] = []
    n = len(sessions)
    _write_ingest_state(
        rt,
        instance.question_id,
        completed=False,
        expected_turns=expected_turns,
        ingested_turns=0,
        accepted_pairs=0,
        rejected_pairs=0,
        failures=[],
    )

    for idx, (date, turns) in enumerate(zip(dates, sessions)):
        ts = _parse_date(date)

        sm._cache.pop(session_key, None)
        session = sm.get_or_create(session_key)

        for turn in turns:
            session.add_message(turn.role, turn.content)
            session.messages[-1]["timestamp"] = ts
            total_turns += 1

        sm.save(session)
        sm._cache.pop(session_key, None)
        session = sm.get_or_create(session_key)

        ingest_result = await _ingest_turns(rt, session_key, idx, turns)
        accepted_pairs += ingest_result.accepted_pairs
        rejected_pairs += ingest_result.rejected_pairs
        failures.extend(ingest_result.failures)
        sm.save(session)

        _write_ingest_state(
            rt,
            instance.question_id,
            completed=False,
            expected_turns=expected_turns,
            ingested_turns=total_turns,
            accepted_pairs=accepted_pairs,
            rejected_pairs=rejected_pairs,
            failures=failures,
        )

        if on_progress:
            on_progress(idx + 1, n)

    _write_ingest_state(
        rt,
        instance.question_id,
        completed=True,
        expected_turns=expected_turns,
        ingested_turns=total_turns,
        accepted_pairs=accepted_pairs,
        rejected_pairs=rejected_pairs,
        failures=failures,
    )

    logger.info(
        "ingest done: %s sessions=%d turns=%d accepted_pairs=%d rejected_pairs=%d failed_pairs=%d",
        session_key,
        len(sessions),
        total_turns,
        accepted_pairs,
        rejected_pairs,
        len(failures),
    )
    return total_turns
