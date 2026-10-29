"""Persisted servers and the tool identity the host registration receives."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from shiori_sdk.mcp import McpToolInfo

from plugins.mcp.backend.registry import McpServerRegistry


class _Session:
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


class _Processes:
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
    assert stored["servers"]["docs"]["command"] == ["python", "srv.py"]
    assert stored["servers"]["docs"]["env"] == {"K": "V"}
    assert "mcp_docs__echo" in registry.list_servers()

    await registry.remove("docs")

    assert registration.tools == []
    assert json.loads(path.read_text(encoding="utf-8"))["servers"] == {}
