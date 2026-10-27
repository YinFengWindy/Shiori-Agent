from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from shiori_sdk.core.conversation import TurnStarting
from shiori_sdk.core.tools import ToolCalled, ToolSource
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.memory_context import FakeMemoryPluginContext
from shiori_sdk.testing.tools import FakeTools

from plugins.default_memory.backend.plugin import _DefaultMemoryRecorder


def _turn_starting(
    *, retrieved_memory_block: str = "", retrieval_trace: object | None = None
) -> TurnStarting:
    return TurnStarting(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        content="hello",
        timestamp=datetime.now(timezone.utc),
        context_scope=None,
        history=(),
        retrieved_memory_block=retrieved_memory_block,
        retrieval_trace=retrieval_trace,
    )


def _called(
    tool_name: str = "recall_memory",
    *,
    arguments: dict[str, object] | None = None,
    result: str = "{}",
    source: ToolSource = "passive",
) -> ToolCalled:
    return ToolCalled(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        source=source,
        call_id="c1",
        tool_name=tool_name,
        arguments=arguments or {},
        status="success",
        result=result,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


# ── _DefaultMemoryRecorder 单元行为 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_recorder_skips_when_inactive(tmp_path: Path) -> None:
    recorder = _DefaultMemoryRecorder(active=False, data_path=tmp_path / "trace.jsonl")

    await recorder.record_context_prepare(_turn_starting())

    assert not (tmp_path / "trace.jsonl").exists()


@pytest.mark.asyncio
async def test_recorder_records_context_prepare_when_active(tmp_path: Path) -> None:
    data_path = tmp_path / "trace.jsonl"
    recorder = _DefaultMemoryRecorder(active=True, data_path=data_path)
    # TurnStarting freezes a dict trace into a read-only mapping.
    event = _turn_starting(
        retrieved_memory_block="## profile\n- [id1] 摘要文本",
        retrieval_trace=MappingProxyType({"route": "RETRIEVE", "hits": [1]}),
    )

    assert await recorder.record_context_prepare(event) is event

    rows = _read_jsonl(data_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "context_prepare"
    assert rows[0]["session_key"] == "cli:1"
    prepare = rows[0]["context_prepare"]
    assert prepare["injected_items"][0]["id"] == "id1"
    assert prepare["retrieval_trace_raw"] == {"route": "RETRIEVE", "hits": [1]}


@pytest.mark.asyncio
async def test_recall_memory_recorded_only_for_matching_tool_when_active(
    tmp_path: Path,
) -> None:
    data_path = tmp_path / "trace.jsonl"
    recorder = _DefaultMemoryRecorder(active=True, data_path=data_path)

    await recorder.record_recall_memory(_called("other_tool"))
    # Only a passive turn's recall is recorded, as before the event existed.
    await recorder.record_recall_memory(_called(source="proactive"))
    assert _read_jsonl(data_path) == []

    called = _called(
        arguments={"query": "q"}, result=json.dumps({"items": [{"id": "m1"}]})
    )
    assert await recorder.record_recall_memory(called) is called
    rows = _read_jsonl(data_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "recall_memory"
    assert rows[0]["recall_memory"]["count"] == 1


@pytest.mark.asyncio
async def test_setup_provides_the_engine_and_records_until_close(
    tmp_path: Path,
) -> None:
    from typing import Any, cast

    from shiori_sdk.core.memory import MEMORY_ENGINE
    from shiori_sdk.core.models import MAIN_MODEL, MAIN_PROVIDER
    from shiori_sdk.kernel import Kernel
    from shiori_sdk.testing.extensions import FakeConfig

    from plugins.default_memory.backend.engine.prompts import (
        _default_memory_tool_profile,
    )
    from plugins.default_memory.backend.plugin import setup

    kernel = Kernel()
    kernel.provide(MAIN_PROVIDER, cast(Any, object()))
    kernel.provide(MAIN_MODEL, "chat")
    ctx = FakeMemoryPluginContext(
        tmp_path,
        kernel=kernel,
        inject=("main_provider", "main_model"),
        provides=("memory_engine",),
    )
    ctx.config = FakeConfig(
        {"embedding_api_key": "k", "embedding_base_url": "http://embed"}
    )
    ctx.http = object()
    ctx.light_provider = object()
    ctx.light_model = "light"
    ctx.tools = FakeTools()
    await setup(cast(Any, ctx))

    engine = ctx.kernel.get(MEMORY_ENGINE)
    assert engine is not None
    assert engine.describe().name == "default"
    profile = _default_memory_tool_profile()
    specs = {
        "memorize": profile.memorize,
        "forget_memory": profile.forget,
        "recall_memory": profile.recall,
    }
    assert set(ctx.tools.tools) == set(specs)
    for name, spec in specs.items():
        assert spec is not None
        options = ctx.tools.options[name]
        assert options["always_on"] is True
        assert options["risk"] == spec.risk
        assert options["search_hint"] == (spec.search_hint or None)
        assert options["external_allowed"] is False
        assert ctx.tools.tools[name].description == spec.description
    assert set(ctx.rpc.handlers) == {
        "roles.memory.documents",
        "roles.memory.semantic.list",
        "roles.memory.semantic.detail",
    }
    assert set(ctx.rpc.concurrency.values()) == {Concurrency.READ_ONLY}

    await ctx.emit(_turn_starting())
    await ctx.emit(_called())
    path = tmp_path / "plugin-data/default_memory/recall_inspector.jsonl"
    rows = _read_jsonl(path)
    assert [row["kind"] for row in rows] == ["context_prepare", "recall_memory"]
    assert rows[0]["turn_id"] == rows[1]["turn_id"]
    await ctx.aclose()
    await ctx.emit(_called())
    assert len(_read_jsonl(path)) == 2
