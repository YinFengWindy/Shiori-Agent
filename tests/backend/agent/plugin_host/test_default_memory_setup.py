from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from shiori_sdk.lifecycle import AfterToolResultCtx
from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from core.roles import RoleStore
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.packages import stage_plugin_package

PLUGIN_DIR = Path(__file__).resolve().parents[4] / "plugins/default_memory"


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
            event_bus=bus,
            workspace=workspace,
            role_store=RoleStore(workspace),
            memory_engine=memory_engine,
        ),
    )
    return kernel, bus


@pytest.mark.asyncio
async def test_markdown_rpc_is_read_only_and_unloads_with_plugin(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = RoleStore(workspace)
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    root = workspace / "roles" / "mira" / "memory"
    root.mkdir(parents=True)
    (root / "SELF.md").write_text("# Mira", encoding="utf-8")
    kernel, _ = _load_default_memory_kernel(
        tmp_path=tmp_path, memory_engine=None, workspace=workspace
    )
    await kernel.load_all()
    method = "plugin.default_memory.roles.memory.documents"
    assert kernel.rpc.policy_for(method).concurrency is Concurrency.READ_ONLY
    resolved = kernel.rpc.resolve(method)
    assert resolved is not None
    assert resolved[0] == "default_memory"
    result = await resolved[1]({"role_id": "mira"})
    assert (
        next(item for item in result["documents"] if item["name"] == "SELF.md")[
            "content"
        ]
        == "# Mira"
    )
    with pytest.raises(ValueError, match="role not found"):
        await resolved[1]({"role_id": "missing"})
    await kernel.unload("default_memory")
    assert kernel.rpc.resolve(method) is None


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
        memory_engine=SimpleNamespace(
            describe=lambda: SimpleNamespace(name="disabled")
        ),
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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]
