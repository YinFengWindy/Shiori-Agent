from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from shiori_sdk.core.conversation import TurnStarting
from shiori_sdk.core.memory import MEMORY_ENGINE
from shiori_sdk.core.tools import ToolCalled
from agent.plugin_host import PluginGenerationSettings, PluginKernel, PluginRpcRegistry
from agent.tools.registry import ToolRegistry
from tests.support.plugin_kernel import host_kernel
from bus.event_bus import EventBus
from core.roles import RoleStore
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.packages import stage_plugin_package

PLUGIN_DIR = Path(__file__).resolve().parents[4] / "plugins/default_memory"
_CREDENTIALS = {
    "embedding_api_key": "test-key",
    "embedding_base_url": "http://embed.test",
}


def _kernel(
    tmp_path: Path,
    workspace: Path,
    *,
    plugin_config: dict[str, object] | None = None,
    provider: object | None = object(),
    model: str | None = "chat",
    tools: ToolRegistry | None = None,
) -> tuple[PluginKernel, ToolRegistry, PluginRpcRegistry[Any]]:
    root = tmp_path / "plugins"
    root.mkdir()
    stage_plugin_package(PLUGIN_DIR, root / "default_memory")
    bus = EventBus()
    rpc = PluginRpcRegistry(bus)
    registry = tools if tools is not None else ToolRegistry()
    kernel = host_kernel(
        [root],
        settings=PluginGenerationSettings(
            workspace=workspace,
            plugin_configs=(
                {"default_memory": plugin_config} if plugin_config is not None else {}
            ),
        ),
        role_store=RoleStore(workspace),
        tools=registry,
        provider=provider,
        model=model,
        http=object(),
        light_provider=object(),
        light_model="light",
        event_bus=bus,
        rpc=rpc,
    )
    return kernel, registry, rpc


def _state(kernel: PluginKernel) -> dict[str, Any]:
    return next(row for row in kernel.states() if row["id"] == "default_memory")


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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


@pytest.mark.asyncio
async def test_setup_provides_the_engine_tools_and_documents(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = RoleStore(workspace)
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    root = workspace / "roles" / "mira" / "memory"
    root.mkdir(parents=True)
    (root / "SELF.md").write_text("# Mira", encoding="utf-8")
    kernel, tools, rpc = _kernel(tmp_path, workspace, plugin_config=_CREDENTIALS)
    await kernel.load_all()

    assert _state(kernel)["state"] == "ACTIVE"
    engine = kernel.kernel.get(MEMORY_ENGINE)
    assert engine is not None
    assert engine.describe().name == "default"
    assert tools.get_tool("memorize") is not None
    assert tools.get_tool("forget_memory") is not None
    assert tools.get_tool("recall_memory") is not None

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

    data_path = workspace / "plugin-data" / "default_memory" / "recall_inspector.jsonl"
    _ = await kernel.kernel.emit(_turn_starting())
    _ = await kernel.kernel.emit(_recall({"query": "q"}, json.dumps({"items": []})))
    assert [row["kind"] for row in _read_jsonl(data_path)] == [
        "context_prepare",
        "recall_memory",
    ]

    await kernel.unload("default_memory")
    assert rpc.resolve(method) is None
    assert kernel.kernel.get(MEMORY_ENGINE) is None
    _ = await kernel.kernel.emit(_turn_starting())
    _ = await kernel.kernel.emit(_recall({}, "{}"))
    assert len(_read_jsonl(data_path)) == 2


@pytest.mark.asyncio
async def test_missing_embedding_credentials_fail_setup_and_leave_the_socket_empty(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, _, _ = _kernel(tmp_path, workspace, plugin_config={})
    await kernel.load_all()
    state = _state(kernel)
    assert state["state"] == "FAILED"
    assert "凭据" in state["error"]
    assert kernel.kernel.get(MEMORY_ENGINE) is None
    assert not (workspace / "plugin-data" / "default_memory" / "memory2.db").exists()


@pytest.mark.asyncio
async def test_missing_main_provider_blocks_before_setup(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, _, _ = _kernel(
        tmp_path, workspace, plugin_config=_CREDENTIALS, provider=None
    )
    await kernel.load_all()
    state = _state(kernel)
    assert state["state"] == "BLOCKED"
    assert "main_provider" in state["error"]
    assert kernel.kernel.get(MEMORY_ENGINE) is None


@pytest.mark.asyncio
async def test_fingerprint_mismatch_fails_setup_without_rewriting_the_row(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_path = workspace / "plugin-data" / "default_memory" / "memory2.db"
    db_path.parent.mkdir(parents=True)
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE sentinel (note TEXT)")
    connection.execute("INSERT INTO sentinel (note) VALUES ('keep')")
    connection.execute("""
        CREATE TABLE embedding_fingerprint (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            model TEXT NOT NULL,
            dim INTEGER NOT NULL
        )
        """)
    connection.execute(
        "INSERT INTO embedding_fingerprint (id, model, dim) VALUES (1, 'other', 32)"
    )
    connection.commit()
    connection.close()

    kernel, _, _ = _kernel(tmp_path, workspace, plugin_config=_CREDENTIALS)
    await kernel.load_all()
    state = _state(kernel)
    assert state["state"] == "FAILED"
    assert "向量空间" in state["error"]
    assert kernel.kernel.get(MEMORY_ENGINE) is None

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT note FROM sentinel").fetchone() == ("keep",)
        assert connection.execute(
            "SELECT model, dim FROM embedding_fingerprint WHERE id = 1"
        ).fetchone() == ("other", 32)
    finally:
        connection.close()
