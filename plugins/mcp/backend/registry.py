"""One owner for saved servers, connections, selection and admitted calls."""

from __future__ import annotations
import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4
from pydantic import ValidationError
from shiori_sdk.core.mcp_tools import McpToolRegistration
from shiori_sdk.mcp import McpSession, McpToolInfo, McpToolError
from . import operations
from .oauth import OAuthBinding
from .models import HttpTransport
from shiori_sdk.processes import Processes
from shiori_sdk.redaction import redact_secrets
from shiori_sdk.tools import ToolResult
from .api import SourceCall
from .configuration import connection_edit
from .models import (
    McpConfigError,
    McpHttpError,
    ServerConfig,
    ToolSelection,
)
from .store import ServerStore
from .redaction import LaunchRedactor
from .tool import McpToolWrapper


@dataclass
class ServerState:
    """Volatile facts; never used to reconstruct persisted intent."""

    epoch: int = 0
    status: str = "disabled"
    error: str | None = None
    infos: list[McpToolInfo] = field(default_factory=list)
    session: McpSession | None = None
    wrappers: dict[str, McpToolWrapper] = field(default_factory=dict)
    calls: set[asyncio.Task[str | ToolResult]] = field(default_factory=set)
    operation: dict[str, object] | None = None


class McpServerRegistry:
    """Every execution rechecks the saved selection and connection epoch."""

    def __init__(
        self,
        config_path: Path,
        *,
        processes: Processes,
        registration: McpToolRegistration,
        changed: Callable[[], None] = lambda: None,
        active: Callable[[], bool] = lambda: True,
    ):
        self.store = ServerStore(config_path)
        self._oauth: dict[str, tuple[str, OAuthBinding]] = {}
        self._processes, self._registration = processes, registration
        self._changed, self._active = changed, active
        self._states: dict[str, ServerState] = {}
        self._operations: dict[str, asyncio.Task[None]] = {}
        self._closed = False
        self._loaded = False
        self.load_error: str | None = None
        self.instance_id = uuid4().hex

    async def load_and_connect_all(self) -> None:
        """Called after publication; failed servers stay editable in the index."""
        try:
            self.store.load()
            self._loaded = True
        except McpConfigError as error:
            self.load_error = str(error)
            self._changed()
            return
        for server, config in self.store.servers.items():
            self._states[server] = ServerState()
            if config.enabled:
                self.start_operation(server, "connect")
        self._changed()

    def _ready(self) -> None:
        if self._closed or not self._active():
            raise McpConfigError("MCP 插件正在重载或已停用")
        if not self._loaded:
            raise McpConfigError(self.load_error or "MCP 配置尚未读取")

    def _config(self, server: str, revision: object = None) -> ServerConfig:
        self._ready()
        config = self.store.servers.get(server)
        if config is None:
            raise McpConfigError("MCP 服务器不存在")
        if revision is not None and revision != config.revision:
            raise McpConfigError("配置已更新，请重新载入后编辑")
        return config

    def snapshot(self) -> dict[str, object]:
        """Project public settings without argv, env values or credential references."""
        rows: list[dict[str, Any]] = []
        if self.load_error:
            return {
                "instance_id": self.instance_id,
                "servers": [],
                "error": self.load_error,
                "loading": False,
            }
        for server, config in self.store.servers.items():
            state = self._states.setdefault(server, ServerState())
            credentials = self.store.credentials(config)
            rows.append(
                {
                    "id": server,
                    "label": config.label,
                    "revision": config.revision,
                    "enabled": config.enabled,
                    "transport": config.transport.model_dump(),
                    "command_configured": bool(credentials.command),
                    "env_names": sorted(credentials.env),
                    "url_configured": bool(credentials.url),
                    "bearer_configured": bool(credentials.bearer),
                    "header_names": sorted(credentials.headers),
                    "oauth": (
                        self.oauth_binding(server).snapshot()
                        if isinstance(config.transport, HttpTransport)
                        and config.transport.auth == "oauth"
                        else None
                    ),
                    "selection": config.tools.model_dump(),
                    "status": state.status,
                    "error": state.error,
                    "tools": [
                        {"name": info.name, "description": info.description}
                        for info in state.infos
                    ],
                    "operation": state.operation,
                }
            )
        return {
            "instance_id": self.instance_id,
            "servers": rows,
            "error": self.load_error,
            "loading": not self._loaded and self.load_error is None,
        }

    def save(self, payload: dict[str, Any]) -> dict[str, object]:
        """Atomically save intent before starting a connection; preserve omitted secrets."""
        self._ready()
        server = str(payload.get("server_id", ""))
        previous = self.store.servers.get(server)
        if previous:
            self._config(server, payload.get("expected_revision"))
            if payload.get("expected_revision") is None:
                raise McpConfigError("编辑需要配置修订")
        elif not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", server):
            raise McpConfigError("服务器 ID 需为 1–40 个字母、数字、下划线或短横线")
        raw = payload.get("config", {})
        edits = payload.get("credentials", {})
        try:
            old = self.store.credentials(previous) if previous else None
            transport, credentials = connection_edit(
                raw.get(
                    "transport",
                    previous.transport.model_dump() if previous else {"kind": "stdio"},
                ),
                edits,
                old,
            )
            label = raw.get("label", server)
            if not isinstance(label, str) or not label.strip():
                raise ValueError("Invalid label")
            selection = ToolSelection.model_validate(
                raw.get("tools", {"mode": "all", "names": []})
            )
            ref = (
                previous.credential_ref
                if previous and credentials == old
                else self.store.write_credentials(credentials)
            )
            config = ServerConfig(
                label=label.strip(),
                revision=previous.revision + 1 if previous else 1,
                enabled=raw.get("enabled", True),
                transport=transport,
                tools=selection,
                credential_ref=ref,
            )
        except McpConfigError:
            raise
        except (ValidationError, TypeError, AttributeError, ValueError):
            raise McpConfigError(
                "服务器设置无效，请检查连接参数、凭据与工具选择"
            ) from None
        self.store.commit({**self.store.servers, server: config})
        state = self._states.setdefault(server, ServerState())
        reconnect = (
            previous is None
            or previous.transport != config.transport
            or previous.credential_ref != config.credential_ref
            or previous.enabled != config.enabled
        )
        if reconnect:
            if (
                server in self._oauth
                and previous
                and (
                    previous.transport != config.transport
                    or previous.credential_ref != config.credential_ref
                )
            ):
                _, binding = self._oauth.pop(server)
                binding.invalidate(clear=True)
            self.start_operation(server, "connect" if config.enabled else "disable")
        else:
            self._register(server, state)
            self._changed()
        return self.snapshot()

    def set_enabled(
        self, server: str, enabled: object, revision: object
    ) -> dict[str, object]:
        """Persist the switch and immediately invalidate old tool references."""
        config = self._config(server, revision)
        if not isinstance(enabled, bool):
            raise McpConfigError("启用状态必须是布尔值")
        updated = config.model_copy(
            update={"enabled": enabled, "revision": config.revision + 1}
        )
        self.store.commit({**self.store.servers, server: updated})
        self.start_operation(server, "connect" if enabled else "disable")
        return self.snapshot()

    def delete(self, server: str, revision: object) -> dict[str, object]:
        """Delete offline servers too; close admission before asynchronous cleanup."""
        self._config(server, revision)
        remaining = dict(self.store.servers)
        del remaining[server]
        if server in self._oauth:
            self._oauth[server][1].invalidate(clear=True)
        self.store.commit(remaining)
        self.start_operation(server, "delete")
        return self.snapshot()

    def oauth_binding(self, server: str) -> OAuthBinding:
        """Return the same provider for connects, tests and admitted tool calls."""
        config = self.store.servers[server]
        if (
            not isinstance(config.transport, HttpTransport)
            or config.transport.auth != "oauth"
        ):
            raise McpConfigError("服务器未配置 OAuth")
        cached = self._oauth.get(server)
        if cached is None or cached[0] != config.credential_ref:
            binding = OAuthBinding(
                self.store.private / "oauth" / f"{config.credential_ref}.json",
                self.store.credentials(config),
                self._changed,
            )
            self._oauth[server] = (config.credential_ref, binding)
        return self._oauth[server][1]

    def _invalidate(self, server: str) -> int:
        state = self._states.setdefault(server, ServerState())
        state.epoch += 1
        self._unregister(state)
        for task in tuple(state.calls):
            task.cancel()
        return state.epoch

    def start_operation(self, server: str, kind: str) -> dict[str, object]:
        """Start one finite management operation without blocking its RPC."""
        return operations.start_operation(self, server, kind)

    def cancel_operation(self, server: str) -> dict[str, object]:
        """Cancel owned work while keeping its persisted configuration."""
        return operations.cancel_operation(self, server)

    async def wait_operations(self) -> None:
        """Join current operations for compatibility callers and shutdown."""
        await operations.wait_operations(self)

    def _unregister(self, state: ServerState) -> None:
        for wrapper in state.wrappers.values():
            self._registration.remove(wrapper.name)
        state.wrappers.clear()

    def _register(self, server: str, state: ServerState) -> None:
        self._unregister(state)
        config = self.store.servers[server]
        if not config.enabled or state.status != "connected":
            return
        try:
            for info in state.infos:
                if config.tools.allows(info.name):
                    wrapper = McpToolWrapper(server, self, info, state.epoch)
                    self._registration.add(wrapper, server=server)
                    state.wrappers[info.name] = wrapper
        except Exception:
            self._unregister(state)
            state.status, state.error = "error", "工具登记失败"
            raise

    async def call(
        self,
        server: str,
        tool: str,
        arguments: dict[str, object],
        *,
        timeout: float | None = None,
        retry_on_transport: bool = False,
    ) -> str | ToolResult:
        """Sources enter the same registered and host-gated wrapper as chat."""
        self._config(server)
        wrapper = self._states[server].wrappers.get(tool)
        if wrapper is None:
            raise McpConfigError("服务器未连接、已停用或工具未获允许")
        return await wrapper.execute(SourceCall(arguments, timeout, retry_on_transport))

    async def call_checked(
        self, server: str, tool: str, epoch: int, request: SourceCall
    ) -> str | ToolResult:
        """Reject stale references at execution, including after filtering or disabling."""
        config = self._config(server)
        state = self._states[server]
        if (
            not config.enabled
            or not config.tools.allows(tool)
            or state.epoch != epoch
            or state.status != "connected"
            or state.session is None
        ):
            raise McpConfigError("MCP 工具已失效，请重新选择工具")
        redactor = self._redactor(server)
        task = asyncio.create_task(
            state.session.call(tool, request.arguments, timeout=request.timeout)
        )
        state.calls.add(task)
        try:
            result = await task
            if isinstance(result, ToolResult):
                return ToolResult(
                    redactor.text(result.text),
                    result.content_blocks,
                    redactor.data(result.structured_content),
                )
            return redactor.text(result)
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            raise McpConfigError("MCP 调用已取消") from None
        except Exception as error:
            if isinstance(error, McpHttpError) and state.epoch == epoch:
                self._invalidate(server)
                state.status, state.error = "error", str(error)
                self._changed()
            transport = isinstance(
                error, (ConnectionError, BrokenPipeError, EOFError, OSError)
            ) and not isinstance(error, TimeoutError)
            if transport and state.epoch == epoch:
                if request.retry_on_transport and self._config(server).enabled:
                    # A retry is the same finite connection operation as a UI
                    # reconnect. Replacement cancels it and owns the new epoch.
                    self.start_operation(server, "connect")
                    retry_epoch = state.epoch
                    reconnect = self._operations[server]
                    try:
                        await asyncio.shield(reconnect)
                    except asyncio.CancelledError:
                        caller = asyncio.current_task()
                        if caller is not None and caller.cancelling():
                            raise
                        raise McpConfigError("MCP 重连已被替换或取消") from None
                    if state.epoch != retry_epoch:
                        raise McpConfigError("MCP 重连已被替换")
                    if state.status != "connected":
                        raise McpConfigError(state.error or "MCP 重连失败")
                    return await self.call(
                        server, tool, request.arguments, timeout=request.timeout
                    )
                self._invalidate(server)
                state.status, state.error = "error", self._safe_error(error)
                self._changed()
            if isinstance(error, McpToolError):
                raise McpToolError(
                    server=server,
                    tool_name=tool,
                    # Generic credential heuristics belong to diagnostics,
                    # never successful MCP payloads or their opaque tokens.
                    message=redact_secrets(redactor.text(error.message)),
                    code=error.code,
                ) from None
            if isinstance(error, TimeoutError):
                raise TimeoutError("MCP 工具调用超时") from None
            if transport:
                raise ConnectionError("MCP 连接已断开") from None
            raise McpConfigError(self._safe_error(error)) from None
        finally:
            state.calls.discard(task)

    def _redactor(self, server: str) -> LaunchRedactor:
        """Capture launch material and the existing OAuth binding, without opening one."""
        oauth = self._oauth.get(server)
        return LaunchRedactor(
            self.store.credentials(self.store.servers[server]),
            additional_values=oauth[1].secrets if oauth else None,
        )

    def _redact(self, server: str, text: str) -> str:
        return self._redactor(server).text(text)

    def _scrub(self, server: str, value: Any) -> Any:
        return self._redactor(server).data(value)

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(error, McpConfigError):
            return str(error)
        if isinstance(error, FileNotFoundError):
            return "找不到 MCP 启动程序或工作目录"
        if isinstance(error, TimeoutError):
            return "MCP 连接或调用超时"
        if isinstance(error, (ConnectionError, OSError, EOFError)):
            return "MCP 连接失败，请检查连接地址或启动程序"
        return "MCP 操作失败，请检查服务器设置"

    async def shutdown(self) -> None:
        """Close admission before cancelling operations and owned connections."""
        self._closed = True
        for _, binding in self._oauth.values():
            binding.invalidate()
        for server in self._states:
            self._invalidate(server)
        for task in self._operations.values():
            task.cancel()
        await self.wait_operations()
        await asyncio.gather(
            *(operations.close_session(self, state) for state in self._states.values())
        )
        for _, binding in self._oauth.values():
            await binding.finish()
        if self._loaded:
            self.store.prune_credentials()

    async def add(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> str:
        """Compatibility management tool; failed connections still save the record."""
        if not self._loaded:
            await self.load_and_connect_all()
        if name in self.store.servers:
            return "MCP 服务器已存在，请在设置页编辑"
        self.save(
            {
                "server_id": name,
                "config": {"label": name, "transport": {"kind": "stdio", "cwd": cwd}},
                "credentials": {
                    "command": {"op": "replace", "value": command},
                    "env": {"op": "replace", "value": env or {}},
                },
            }
        )
        await self.wait_operations()
        return self.list_servers()

    async def remove(self, name: str) -> str:
        """Compatibility tool deletes both offline and connected records."""
        self.delete(name, None)
        await self.wait_operations()
        return "MCP 服务器已删除"

    def list_servers(self) -> str:
        """Model-safe status; never project connection credentials."""
        return (
            "\n".join(
                f"- {config.label}（{self._states[server].status}）："
                + ", ".join(
                    wrapper.name for wrapper in self._states[server].wrappers.values()
                )
                for server, config in self.store.servers.items()
            )
            or "当前没有 MCP 服务器"
        )
