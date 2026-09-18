from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.lifecycle.types import AfterToolResultCtx, BeforeTurnCtx
from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from plugins.default_memory.backend.plugin import (
    ContextPrepareRecordModule,
    _DefaultMemoryRecorder,
)


def test_missing_workspace_rejects_package_log_fallback(tmp_path):
    from plugins.default_memory.backend.plugin import _data_path

    with pytest.raises(RuntimeError, match="不能写入安装包"):
        _data_path(plugin_dir=tmp_path, workspace=None)
    assert not (tmp_path / ".data").exists()


PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _before_turn_ctx(**overrides: object) -> BeforeTurnCtx:
    defaults: dict[str, object] = dict(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        content="hello",
        timestamp=datetime.now(timezone.utc),
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
    )
    defaults.update(overrides)
    return BeforeTurnCtx(**defaults)


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


# ── setup(ctx) 通过真实内核装配的端到端验证 ────────────────────────────────


def _load_default_memory_kernel(
    *, tmp_path: Path, memory_engine: object, workspace: Path
) -> tuple[PluginKernel, EventBus]:
    root = tmp_path / "plugins"
    root.mkdir()
    stage_plugin_package(PLUGIN_DIR, root / "default_memory")
    bus = EventBus()
    kernel = PluginKernel(
        [root],
        services=HostServices(
            event_bus=bus, workspace=workspace, memory_engine=memory_engine
        ),
    )
    return kernel, bus


@pytest.mark.asyncio
async def test_setup_wires_before_turn_module_and_tool_result_event(
    tmp_path: Path,
) -> None:
    """setup(ctx) 必须与旧 DefaultMemoryInspector 等价：贡献 before_turn 模块，
    并把 recall_memory 工具结果记录经 AFTER_TOOL_RESULT 事件接线。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, bus = _load_default_memory_kernel(
        tmp_path=tmp_path,
        memory_engine=SimpleNamespace(describe=lambda: SimpleNamespace(name="default")),
        workspace=workspace,
    )
    await kernel.load_all()

    assert [type(m).__name__ for m in kernel.before_turn_modules] == [
        "ContextPrepareRecordModule"
    ]

    data_path = workspace / "plugin-data" / "default_memory" / "recall_inspector.jsonl"
    _ = await bus.emit(
        AfterToolResultCtx(
            session_key="cli:1",
            channel="cli",
            chat_id="1",
            tool_name="recall_memory",
            arguments={"query": "q"},
            result=json.dumps({"items": []}),
            status="ok",
        )
    )
    rows = _read_jsonl(data_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "recall_memory"

    # 卸载后贡献必须整体撤回，证明 phase 槽位与事件订阅都挂在插件作用域上
    _ = await kernel.unload("default_memory")
    assert kernel.before_turn_modules == []
    _ = await bus.emit(
        AfterToolResultCtx(
            session_key="cli:1",
            channel="cli",
            chat_id="1",
            tool_name="recall_memory",
            arguments={},
            result="{}",
            status="ok",
        )
    )
    assert len(_read_jsonl(data_path)) == 1


@pytest.mark.asyncio
async def test_setup_still_wires_module_but_recorder_is_inactive_for_other_engine(
    tmp_path: Path,
) -> None:
    """引擎不是 default 时模块仍会贡献（对齐旧行为），但记录内部被抑制。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, bus = _load_default_memory_kernel(
        tmp_path=tmp_path,
        memory_engine=SimpleNamespace(describe=lambda: SimpleNamespace(name="akasha")),
        workspace=workspace,
    )
    await kernel.load_all()

    assert [type(m).__name__ for m in kernel.before_turn_modules] == [
        "ContextPrepareRecordModule"
    ]

    _ = await bus.emit(
        AfterToolResultCtx(
            session_key="cli:1",
            channel="cli",
            chat_id="1",
            tool_name="recall_memory",
            arguments={},
            result="{}",
            status="ok",
        )
    )
    assert not (
        workspace / "plugin-data" / "default_memory" / "recall_inspector.jsonl"
    ).exists()
