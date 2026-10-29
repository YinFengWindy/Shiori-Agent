"""User MCP servers: persistence, reconnect, and tool registration.

Stdio stays on the host ``PROCESSES.mcp()`` session. Command, env and cwd are
stored here; the session protocol does not expose them.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from shiori_sdk.core.mcp_tools import McpToolRegistration
from shiori_sdk.mcp import McpSession, McpToolInfo
from shiori_sdk.processes import Processes

from .tool import McpToolWrapper

logger = logging.getLogger(__name__)


class McpServerRegistry:
    """Connects configured servers and registers their tools as ``source_type=mcp``."""

    def __init__(
        self,
        config_path: Path,
        *,
        processes: Processes,
        registration: McpToolRegistration,
    ) -> None:
        self._config_path = config_path
        self._processes = processes
        self._registration = registration
        self._sessions: dict[str, McpSession] = {}
        self._configs: dict[str, dict[str, Any]] = {}
        self._server_tools: dict[str, list[str]] = {}
        self._connect_task: asyncio.Task[None] | None = None

    def start_connect_all_background(self) -> asyncio.Task[None]:
        """Reconnect every saved server without blocking plugin setup."""
        if self._connect_task is None or self._connect_task.done():
            self._connect_task = asyncio.create_task(
                self.load_and_connect_all(), name="mcp_connect_all"
            )
        return self._connect_task

    async def load_and_connect_all(self) -> None:
        """Reconnect every server recorded in ``mcp_servers.json``."""

        async def connect_one(name: str, cfg: dict[str, Any]) -> None:
            try:
                await self._connect(
                    name, list(cfg["command"]), cfg.get("env"), cfg.get("cwd")
                )
            except Exception as exc:
                logger.error("[mcp] 重连 %r 失败: %s", name, exc)

        await asyncio.gather(
            *(connect_one(name, cfg) for name, cfg in self._load_raw_configs().items())
        )

    async def shutdown(self) -> None:
        """Cancel a pending reconnect and disconnect every session."""
        if self._connect_task is not None and not self._connect_task.done():
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass
        sessions = list(self._sessions.values())
        tool_names = [
            tool_name for names in self._server_tools.values() for tool_name in names
        ]
        self._sessions.clear()
        self._configs.clear()
        self._server_tools.clear()
        for tool_name in tool_names:
            self._registration.remove(tool_name)
        await asyncio.gather(
            *(session.disconnect() for session in sessions), return_exceptions=True
        )

    async def add(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> str:
        """Connect ``name`` and persist it. An existing name is left unchanged."""
        if name in self._sessions:
            return f"MCP server {name!r} 已存在。如需更新，请先 mcp_remove 再重新添加。"
        try:
            tool_names = await self._connect(name, command, env, cwd)
        except Exception as exc:
            return f"连接 MCP server {name!r} 失败：{exc}"
        self._save()
        return (
            f"已连接 MCP server {name!r}，注册了 {len(tool_names)} 个工具：\n"
            + "\n".join(f"- {n}" for n in tool_names)
        )

    async def remove(self, name: str) -> str:
        """Disconnect ``name`` and drop its tools."""
        if name not in self._sessions:
            return f"MCP server {name!r} 不存在，当前已注册：{list(self._sessions) or '无'}"
        for tool_name in self._server_tools.pop(name, []):
            self._registration.remove(tool_name)
        await self._sessions.pop(name).disconnect()
        self._configs.pop(name, None)
        self._save()
        return f"已注销 MCP server {name!r}。"

    def list_servers(self) -> str:
        """One line per connected server."""
        if not self._sessions:
            return "当前没有已注册的 MCP server。"
        lines = []
        for name in self._sessions:
            tools = self._server_tools.get(name, [])
            lines.append(f"- {name}（{len(tools)} 个工具）：{', '.join(tools) or '无'}")
        return "\n".join(lines)

    async def _connect(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None,
        cwd: str | None,
    ) -> list[str]:
        session = self._processes.mcp(name, command, env, cwd)
        infos = await session.connect()
        tool_names: list[str] = []
        for info in infos:
            wrapper = McpToolWrapper(name, session, _tool_info(info))
            self._registration.add(wrapper, server=name)
            tool_names.append(wrapper.name)
        self._sessions[name] = session
        self._configs[name] = {
            "command": list(command),
            "env": dict(env or {}),
            "cwd": cwd,
        }
        self._server_tools[name] = tool_names
        return tool_names

    def _load_raw_configs(self) -> dict[str, Any]:
        if not self._config_path.exists():
            return {}
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[mcp] 读取配置失败 %s: %s", self._config_path, exc)
            return {}
        servers = data.get("servers")
        return servers if isinstance(servers, dict) else {}

    def _save(self) -> None:
        payload = {"servers": self._configs}
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _tool_info(info: object) -> McpToolInfo:
    if isinstance(info, McpToolInfo):
        return info
    return McpToolInfo(
        name=str(getattr(info, "name", "")),
        description=str(getattr(info, "description", "")),
        input_schema=dict(getattr(info, "input_schema", {}) or {}),
    )
