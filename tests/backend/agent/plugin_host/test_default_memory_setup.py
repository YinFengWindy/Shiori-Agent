from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from shiori_sdk.core.conversation import TurnStarting
from shiori_sdk.core.tools import ToolCalled
from agent.plugin_host import PluginGenerationSettings, PluginKernel, PluginRpcRegistry
from agent.tools.registry import ToolRegistry
from tests.support.plugin_kernel import host_kernel
from bus.event_bus import EventBus
from core.roles import RoleStore
from shiori_sdk.memory.engine import MemoryToolProfile
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.packages import stage_plugin_package

PLUGIN_DIR = Path(__file__).resolve().parents[4] / "plugins/default_memory"


# ── setup(ctx) 通过真实内核装配的端到端验证 ────────────────────────────────


def _load_default_memory_kernel(
    *, tmp_path: Path, memory_engine: object, workspace: Path
) -> tuple[PluginKernel, EventBus, PluginRpcRegistry[Any]]:
    root = tmp_path / "plugins"
    root.mkdir()
    stage_plugin_package(PLUGIN_DIR, root / "default_memory")
    bus = EventBus()
    rpc = PluginRpcRegistry(bus)
    kernel = host_kernel(
        [root],
        settings=PluginGenerationSettings(workspace=workspace),
        role_store=RoleStore(workspace),
        tools=ToolRegistry(),
        memory_engine=memory_engine,
        event_bus=bus,
        rpc=rpc,
    )
    return kernel, bus, rpc


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
    kernel, _, rpc = _load_default_memory_kernel(
        tmp_path=tmp_path, memory_engine=None, workspace=workspace
    )
    await kernel.load_all()
    method = "plugin.default_memory.roles.memory.documents"
    assert rpc.policy_for(method).concurrency is Concurrency.READ_ONLY
    resolved = rpc.resolve(method)
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
    assert rpc.resolve(method) is None


def _turn_starting() -> TurnStarting:
    return TurnStarting(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        content="hello",
        timestamp=datetime.now(timezone.utc),
        context_scope=None,
        history=(),
        retrieved_memory_block="",
        retrieval_trace=None,
    )


def _recall(arguments: dict[str, object], result: str) -> ToolCalled:
    return ToolCalled(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        source="passive",
        call_id="c1",
        tool_name="recall_memory",
        arguments=arguments,
        status="success",
        result=result,
    )


@pytest.mark.asyncio
async def test_setup_records_turn_retrieval_and_tool_results_until_unload(
    tmp_path: Path,
) -> None:
    """setup(ctx) 与旧 DefaultMemoryInspector 等价：本代内核的 ``TurnStarting``
    记录检索，``ToolCalled`` 记录 recall_memory 结果，卸载后都不再记录。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, _, _ = _load_default_memory_kernel(
        tmp_path=tmp_path,
        memory_engine=SimpleNamespace(
            describe=lambda: SimpleNamespace(name="default"),
            tool_profile=MemoryToolProfile,
        ),
        workspace=workspace,
    )
    await kernel.load_all()

    data_path = workspace / "plugin-data" / "default_memory" / "recall_inspector.jsonl"
    _ = await kernel.kernel.emit(_turn_starting())
    _ = await kernel.kernel.emit(_recall({"query": "q"}, json.dumps({"items": []})))
    rows = _read_jsonl(data_path)
    assert [row["kind"] for row in rows] == ["context_prepare", "recall_memory"]

    # 卸载后订阅整体撤回，证明它们都挂在插件作用域上
    _ = await kernel.unload("default_memory")
    _ = await kernel.kernel.emit(_turn_starting())
    _ = await kernel.kernel.emit(_recall({}, "{}"))
    assert len(_read_jsonl(data_path)) == 2


@pytest.mark.asyncio
async def test_recorder_is_inactive_for_another_engine(tmp_path: Path) -> None:
    """引擎不是 default 时插件照常装配，但不记录任何轨迹。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, _, _ = _load_default_memory_kernel(
        tmp_path=tmp_path,
        memory_engine=SimpleNamespace(
            describe=lambda: SimpleNamespace(name="disabled"),
            tool_profile=MemoryToolProfile,
        ),
        workspace=workspace,
    )
    await kernel.load_all()

    _ = await kernel.kernel.emit(_turn_starting())
    _ = await kernel.kernel.emit(_recall({}, "{}"))
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
