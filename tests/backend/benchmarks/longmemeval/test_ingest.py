from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.memory.engine import MemoryIngestResult
from benchmarks.longmemeval.dataset import LMEInstance, LMETurn
from benchmarks.longmemeval.ingest import _ingest_turns, ingest_instance


class _FakeEngine:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = outcomes
        self.requests = []

    async def ingest(self, request):
        self.requests.append(request)
        outcome = self._outcomes[len(self.requests) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeSession:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})


class _FakeSessionManager:
    def __init__(self) -> None:
        self._cache: dict[str, _FakeSession] = {}
        self._sessions: dict[str, _FakeSession] = {}

    def get_or_create(self, key: str) -> _FakeSession:
        session = self._sessions.setdefault(key, _FakeSession())
        self._cache[key] = session
        return session

    def save(self, session: _FakeSession) -> None:
        return None


def _runtime(tmp_path: Path, engine: _FakeEngine):
    return SimpleNamespace(
        workspace=tmp_path,
        core=SimpleNamespace(
            memory_runtime=SimpleNamespace(engine=engine),
            session_manager=_FakeSessionManager(),
        ),
    )


@pytest.mark.asyncio
async def test_ingest_turns_records_timeout_and_continues_to_later_pairs(tmp_path: Path):
    engine = _FakeEngine(
        [
            MemoryIngestResult(accepted=True),
            TimeoutError("provider request timed out"),
            MemoryIngestResult(accepted=False, summary="worker unavailable"),
        ]
    )
    result = await _ingest_turns(
        _runtime(tmp_path, engine),
        "lme:case-1",
        2,
        [
            LMETurn("user", "first user"),
            LMETurn("assistant", "first assistant"),
            LMETurn("user", "second user"),
            LMETurn("assistant", "second assistant"),
            LMETurn("user", "third user"),
            LMETurn("assistant", "third assistant"),
        ],
    )

    assert result.accepted_pairs == 1
    assert result.rejected_pairs == 1
    assert len(result.failures) == 1
    assert result.failures[0].source_ref == "lme:case-1#ingest:2:1"
    assert "TimeoutError" in result.failures[0].error
    assert [request.metadata["source_ref"] for request in engine.requests] == [
        "lme:case-1#ingest:2:0",
        "lme:case-1#ingest:2:1",
        "lme:case-1#ingest:2:2",
    ]
    assert engine.requests[0].scope.role_id == "benchmark"


@pytest.mark.asyncio
async def test_ingest_instance_persists_recoverable_failures_without_replaying_pairs(
    tmp_path: Path,
):
    engine = _FakeEngine(
        [
            TimeoutError("provider request timed out"),
            MemoryIngestResult(accepted=True),
        ]
    )
    runtime = _runtime(tmp_path, engine)
    instance = LMEInstance(
        question_id="case-2",
        question_type="single-session-user",
        question="What is the fact?",
        answer="A fact",
        question_date="2026-01-01",
        haystack_session_ids=["a", "b"],
        haystack_dates=["2026-01-01", "2026-01-02"],
        haystack_sessions=[
            [LMETurn("user", "first"), LMETurn("assistant", "one")],
            [LMETurn("user", "second"), LMETurn("assistant", "two")],
        ],
    )

    assert await ingest_instance(runtime, instance) == 4

    state = json.loads((tmp_path / "ingest_state.json").read_text(encoding="utf-8"))
    assert state == {
        "question_id": "case-2",
        "completed": True,
        "expected_turns": 4,
        "ingested_turns": 4,
        "accepted_pairs": 1,
        "rejected_pairs": 0,
        "failed_pairs": 1,
        "failures": [
            {
                "pair_index": 0,
                "source_ref": "lme:case-2#ingest:0:0",
                "error": "TimeoutError: provider request timed out",
            }
        ],
    }
    assert len(engine.requests) == 2
