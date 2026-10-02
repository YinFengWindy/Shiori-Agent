from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from shiori_sdk.lifecycle import AfterToolResultCtx
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.memory_context import FakeMemoryPluginContext

from plugins.default_memory.backend.plugin import (
    ContextPrepareRecordModule,
    _DefaultMemoryRecorder,
)

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _before_turn_ctx(**overrides: object):
    defaults: dict[str, object] = dict(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        content="hello",
        timestamp=datetime.now(timezone.utc),
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


# ── _DefaultMemoryRecorder / ContextPrepareRecordModule 单元行为 ──────────────


def test_recorder_skips_when_inactive(tmp_path: Path) -> None:
    recorder = _DefaultMemoryRecorder(active=False, data_path=tmp_path / "trace.jsonl")

    recorder.record_context_prepare(_before_turn_ctx())

    assert not (tmp_path / "trace.jsonl").exists()


def test_recorder_records_context_prepare_when_active(tmp_path: Path) -> None:
    data_path = tmp_path / "trace.jsonl"
    recorder = _DefaultMemoryRecorder(active=True, data_path=data_path)

    recorder.record_context_prepare(
        _before_turn_ctx(retrieved_memory_block="## profile\n- [id1] 摘要文本")
    )

    rows = _read_jsonl(data_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "context_prepare"
    assert rows[0]["session_key"] == "cli:1"
    assert rows[0]["context_prepare"]["injected_items"][0]["id"] == "id1"


@pytest.mark.asyncio
async def test_context_prepare_module_delegates_to_recorder(tmp_path: Path) -> None:
    data_path = tmp_path / "trace.jsonl"
    recorder = _DefaultMemoryRecorder(active=True, data_path=data_path)
    module = ContextPrepareRecordModule(recorder)
    frame = SimpleNamespace(slots={"session:ctx": _before_turn_ctx()})

    result = await module.run(frame)

    assert result is frame
    assert len(_read_jsonl(data_path)) == 1


@pytest.mark.asyncio
async def test_recall_memory_recorded_only_for_matching_tool_when_active(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "trace.jsonl"
    recorder = _DefaultMemoryRecorder(active=True, data_path=data_path)

    await recorder.record_recall_memory(
        AfterToolResultCtx(
            session_key="cli:1",
            channel="cli",
            chat_id="1",
            tool_name="other_tool",
            arguments={},
            result="{}",
            status="ok",
        )
    )
    assert _read_jsonl(data_path) == []

    await recorder.record_recall_memory(
        AfterToolResultCtx(
            session_key="cli:1",
            channel="cli",
            chat_id="1",
            tool_name="recall_memory",
            arguments={"query": "q"},
            result=json.dumps({"items": [{"id": "m1"}]}),
            status="ok",
        )
    )
    rows = _read_jsonl(data_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "recall_memory"
    assert rows[0]["recall_memory"]["count"] == 1


@pytest.mark.asyncio
async def test_setup_registers_scoped_documents_semantics_and_observation(tmp_path):
    from plugins.default_memory.backend.plugin import setup

    ctx = FakeMemoryPluginContext(tmp_path)
    await setup(ctx)
    assert set(ctx.rpc.handlers) == {
        "roles.memory.documents",
        "roles.memory.semantic.list",
        "roles.memory.semantic.detail",
    }
    assert set(ctx.rpc.concurrency.values()) == {Concurrency.READ_ONLY}
    assert len(ctx.lifecycle.modules["before_turn"]) == 1
    await ctx.events.emit(
        AfterToolResultCtx("cli:1", "cli", "1", "recall_memory", {}, "{}", "ok")
    )
    path = tmp_path / "plugin-data/default_memory/recall_inspector.jsonl"
    assert len(_read_jsonl(path)) == 1
    events = ctx.events
    await ctx.aclose()
    await events.emit(
        AfterToolResultCtx("cli:1", "cli", "1", "recall_memory", {}, "{}", "ok")
    )
    assert len(_read_jsonl(path)) == 1
