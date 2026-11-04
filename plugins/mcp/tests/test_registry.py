"""Persisted servers and the tool identity the host registration receives."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from shiori_sdk.mcp import McpToolInfo
from shiori_sdk.testing.processes import FakeMcpSession, FakeProcesses

from plugins.mcp.backend.registry import McpServerRegistry


class _Session(FakeMcpSession):
    def __init__(self, name: str, command: list[str], env, cwd) -> None:
        self.name = name
        self.command = command
        self.env = env
        self.cwd = cwd
        self.disconnected = False

    async def connect(self) -> list[McpToolInfo]:
        return [
            McpToolInfo(
                name="echo", description="Echo", input_schema={"type": "object"}
            )
        ]

    async def call(
        self, tool_name: str, arguments: dict, *, timeout: float | None = None
    ):
        return tool_name

    async def disconnect(self) -> None:
        self.disconnected = True


class _Processes(FakeProcesses):
    def mcp(self, name, command, env=None, cwd=None, **_kwargs):
        return _Session(name, command, env, cwd)


class _Registration:
    def __init__(self) -> None:
        self.tools: list[tuple[str, str]] = []

    def add(self, tool, *, server: str, risk: str = "external-side-effect") -> None:
        self.tools.append((tool.name, server))

    def remove(self, name: str) -> None:
        self.tools = [item for item in self.tools if item[0] != name]


@pytest.mark.asyncio
async def test_add_persists_command_and_registers_the_server_tool(tmp_path: Path):
    path = tmp_path / "mcp_servers.json"
    registration = _Registration()
    registry = McpServerRegistry(
        path, processes=_Processes(), registration=registration
    )

    added = await registry.add("docs", ["python", "srv.py"], env={"K": "V"}, cwd="/tmp")

    assert "docs" in added
    assert registration.tools == [("mcp_docs__echo", "docs")]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["schema_version"] == 2
    private = registry.store.credentials(registry.store.servers["docs"])
    assert private.command == ["python", "srv.py"]
    assert private.env == {"K": "V"}
    assert "srv.py" not in json.dumps(registry.snapshot())
    assert "mcp_docs__echo" in registry.list_servers()

    await registry.remove("docs")

    assert registration.tools == []
    assert json.loads(path.read_text(encoding="utf-8"))["servers"] == {}


async def test_migration_keeps_offline_server_and_private_values(tmp_path, monkeypatch):
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps(
            {
                "servers": {
                    "offline": {
                        "command": ["missing", "private-argument"],
                        "env": {"TOKEN": "private-token"},
                        "cwd": "/wanted",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    async def fail(_self):
        raise OSError("private-token private-argument")

    monkeypatch.setattr(_Session, "connect", fail)
    registry = McpServerRegistry(
        path, processes=_Processes(), registration=_Registration()
    )
    await registry.load_and_connect_all()
    await registry.wait_operations()
    snapshot = registry.snapshot()
    assert snapshot["servers"][0]["status"] == "error"
    assert snapshot["servers"][0]["transport"]["cwd"] == "/wanted"
    assert "private-token" not in json.dumps(snapshot)
    assert "private-argument" not in path.read_text(encoding="utf-8")
    await registry.add("other", ["another"])
    assert set(json.loads(path.read_text(encoding="utf-8"))["servers"]) == {
        "offline",
        "other",
    }
    await registry.remove("offline")
    assert set(registry.store.servers) == {"other"}
    await registry.shutdown()


async def test_filter_disable_and_reconnect_reject_captured_tool(tmp_path):
    registry = McpServerRegistry(
        tmp_path / "mcp_servers.json",
        processes=_Processes(),
        registration=_Registration(),
    )
    await registry.add("docs", ["server"])
    captured = registry._states["docs"].wrappers["echo"]
    assert await captured.execute() == "echo"
    registry.save(
        {
            "server_id": "docs",
            "expected_revision": 1,
            "config": {"tools": {"mode": "selected", "names": []}},
        }
    )
    with pytest.raises(ValueError, match="失效"):
        await captured.execute()
    with pytest.raises(ValueError, match="允许"):
        await registry.call("docs", "echo", {})
    registry.save(
        {
            "server_id": "docs",
            "expected_revision": 2,
            "config": {"tools": {"mode": "all"}},
        }
    )
    assert await registry.call("docs", "echo", {}) == "echo"
    registry.set_enabled("docs", False, 3)
    with pytest.raises(ValueError, match="失效"):
        await captured.execute()
    await registry.wait_operations()
    registry.set_enabled("docs", True, 4)
    await registry.wait_operations()
    with pytest.raises(ValueError, match="失效"):
        await captured.execute()
    assert await registry.call("docs", "echo", {}) == "echo"
    await registry.shutdown()


async def test_only_explicit_transport_retry_replays_and_timeout_is_preserved(
    tmp_path, monkeypatch
):
    attempts = []

    async def call(_self, name, args, *, timeout=None):
        attempts.append((name, timeout))
        if len(attempts) == 1:
            raise ConnectionError("broken")
        return "recovered"

    monkeypatch.setattr(_Session, "call", call)
    registry = McpServerRegistry(
        tmp_path / "mcp_servers.json",
        processes=_Processes(),
        registration=_Registration(),
    )
    await registry.add("docs", ["server"])
    assert (
        await registry.call("docs", "echo", {}, timeout=180, retry_on_transport=True)
        == "recovered"
    )
    assert attempts == [("echo", 180), ("echo", 180)]
    attempts.clear()
    with pytest.raises(ConnectionError):
        await registry.call("docs", "echo", {}, timeout=180)
    assert attempts == [("echo", 180)]
    registry.start_operation("docs", "connect")
    await registry.wait_operations()

    async def timeout(_self, *args, **kwargs):
        attempts.append("timeout")
        raise TimeoutError("deadline")

    monkeypatch.setattr(_Session, "call", timeout)
    with pytest.raises(TimeoutError):
        await registry.call("docs", "echo", {}, retry_on_transport=True)
    assert attempts.count("timeout") == 1
    await registry.shutdown()


async def test_disable_during_connection_cannot_publish_late_tools(
    tmp_path, monkeypatch
):
    entered = asyncio.Event()
    closed = []

    async def connect(_self):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return [McpToolInfo("late", "", {})]

    async def close(self):
        closed.append(self)

    monkeypatch.setattr(_Session, "connect", connect)
    monkeypatch.setattr(_Session, "disconnect", close)
    registration = _Registration()
    registry = McpServerRegistry(
        tmp_path / "mcp_servers.json", processes=_Processes(), registration=registration
    )
    await registry.load_and_connect_all()
    registry.save(
        {
            "server_id": "docs",
            "credentials": {"command": {"op": "replace", "value": ["server"]}},
        }
    )
    await entered.wait()
    registry.set_enabled("docs", False, 1)
    await registry.wait_operations()
    assert registration.tools == []
    assert registry.snapshot()["servers"][0]["status"] == "disabled"
    assert len(closed) == 1
    await registry.shutdown()


async def test_failed_config_commit_and_corrupt_input_leave_previous_data(
    tmp_path, monkeypatch
):
    from plugins.mcp.backend import store

    path = tmp_path / "mcp_servers.json"
    registry = McpServerRegistry(
        path, processes=_Processes(), registration=_Registration()
    )
    await registry.add("docs", ["server"], env={"TOKEN": "old-secret"})
    before = path.read_bytes()
    original = store.atomic_save_json

    def fail_index(target, data):
        if target == path:
            raise OSError("disk unavailable")
        original(target, data)

    monkeypatch.setattr(store, "atomic_save_json", fail_index)
    with pytest.raises(OSError):
        registry.save(
            {
                "server_id": "docs",
                "expected_revision": 1,
                "credentials": {
                    "env": {"op": "replace", "value": {"TOKEN": "new-secret"}}
                },
            }
        )
    assert path.read_bytes() == before
    assert registry.store.credentials(registry.store.servers["docs"]).env == {
        "TOKEN": "old-secret"
    }
    assert await registry.call("docs", "echo", {}) == "echo"
    await registry.shutdown()
    path.write_text("{broken secret", encoding="utf-8")
    fresh = McpServerRegistry(
        path, processes=_Processes(), registration=_Registration()
    )
    await fresh.load_and_connect_all()
    assert fresh.snapshot()["error"]
    with pytest.raises(ValueError):
        fresh.save({"server_id": "other"})
    assert path.read_text(encoding="utf-8") == "{broken secret"
    await fresh.shutdown()


async def test_cancel_before_reconnect_starts_closes_existing_session(tmp_path):
    registry = McpServerRegistry(
        tmp_path / "mcp_servers.json",
        processes=_Processes(),
        registration=_Registration(),
    )
    await registry.add("docs", ["server"])
    session = registry._states["docs"].session
    registry.start_operation("docs", "connect")
    registry.cancel_operation("docs")
    await registry.wait_operations()
    assert session.disconnected
    assert registry._states["docs"].session is None
    assert registry.snapshot()["servers"][0]["status"] == "disconnected"
    assert registry.store.servers["docs"].enabled
    await registry.shutdown()


async def test_private_value_redaction_preserves_binary_tool_content(
    tmp_path, monkeypatch
):
    from shiori_sdk.tools import ToolResult

    image = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAA1AAAA"},
    }

    async def call(_self, *args, **kwargs):
        return ToolResult(
            text="private-token abc1def",
            content_blocks=[image],
            structured_content={"secret": "private-token"},
        )

    monkeypatch.setattr(_Session, "call", call)
    registry = McpServerRegistry(
        tmp_path / "mcp_servers.json",
        processes=_Processes(),
        registration=_Registration(),
    )
    await registry.add("docs", ["server"], env={"FLAG": "1", "TOKEN": "private-token"})
    result = await registry.call("docs", "echo", {})
    assert "private-token" not in result.text
    assert "abc1def" in result.text
    assert result.structured_content == {"secret": "[已隐藏]"}
    assert result.content_blocks == [image]
    await registry.shutdown()
