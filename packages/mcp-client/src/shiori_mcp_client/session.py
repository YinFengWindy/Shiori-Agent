"""Official MCP sessions: discovery, calls, deadlines and context ownership."""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import Any
from mcp.client._transport import Transport

import anyio
import httpx2
from mcp import Client, MCPError
from mcp_types import CallToolResult
from .contracts import (
    McpToolError,
    McpToolInfo,
    McpProtocolError,
    McpHttpError,
    McpAuthenticationRequired,
)
from .observation import CallObservation, CURRENT_CALL, TransportObservation
from .result import decode_tool_result
from shiori_sdk.tools import ToolResult

_DIAGNOSTICS: ContextVar[bool] = ContextVar(
    "shiori_mcp_http_diagnostics", default=False
)
_HTTP_STATUS: ContextVar[list[int] | None] = ContextVar(
    "shiori_mcp_http_status", default=None
)


class _SafeDiagnostics(logging.Filter):
    """SDK logs may contain bodies, headers and chained exceptions; keep metadata only."""

    def filter(self, record: logging.LogRecord) -> bool:
        if _DIAGNOSTICS.get():
            record.msg = "MCP transport diagnostic"
            record.args = ()
            record.exc_info = record.exc_text = record.stack_info = None
        return True


# Filters apply only to tasks executing this adapter, not other httpx2 consumers.
# These are the logging owners in the pinned official SDK and HTTP implementation.
_FILTER = _SafeDiagnostics()
_FILTER_USERS = 0
_LOGGER_NAMES = (
    "mcp.client.streamable_http",
    "mcp.client.client",
    "mcp.client.caching",
    "mcp.client.auth.oauth2",
    "mcp.client.auth.utils",
    "mcp.shared.auth",
    "mcp.shared._httpx_utils",
    "mcp.shared.dispatcher",
    "mcp.shared.jsonrpc_dispatcher",
    "client",
    "httpx2",
    "httpcore2.http11",
    "httpcore2.http2",
    "httpcore2.connection",
    "httpcore2.proxy",
    "httpcore2.socks",
)


def _diagnostics_acquire() -> None:
    global _FILTER_USERS
    if not _FILTER_USERS:
        for name in _LOGGER_NAMES:
            logging.getLogger(name).addFilter(_FILTER)
    _FILTER_USERS += 1


def _diagnostics_release() -> None:
    global _FILTER_USERS
    _FILTER_USERS -= 1
    if not _FILTER_USERS:
        for name in _LOGGER_NAMES:
            logging.getLogger(name).removeFilter(_FILTER)


def _failure(error: BaseException, status: list[int], phase: str) -> Exception:
    """Translate the transport boundary without retaining unsafe exception chains."""
    if isinstance(error, McpAuthenticationRequired):
        return error
    if isinstance(error, BaseExceptionGroup):
        failures = [_failure(item, status, phase) for item in error.exceptions]
        return next(
            (item for item in failures if isinstance(item, McpAuthenticationRequired)),
            next(
                (item for item in failures if isinstance(item, ConnectionError)),
                failures[0],
            ),
        )
    if status and status[-1] in {401, 403}:
        message = "认证未通过" if status[-1] == 401 else "访问被拒绝"
        return McpHttpError(f"MCP {phase}失败（{status[-1]}）：{message}")
    if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
        return TimeoutError(f"MCP {phase}超时")
    if isinstance(
        error,
        (
            httpx2.TransportError,
            ConnectionError,
            anyio.EndOfStream,
            anyio.BrokenResourceError,
            anyio.ClosedResourceError,
        ),
    ):
        return ConnectionError(f"MCP {phase}连接已断开")
    if status and status[-1] >= 400:
        return McpHttpError(f"MCP {phase}失败（{status[-1]}）")
    if isinstance(error, McpProtocolError):
        return error
    return McpProtocolError(f"MCP {phase}失败：响应不符合协议")


class ClientSession:
    """Own the official Client in one task; transports never replay tool calls."""

    def __init__(self, server: str, *, connect_timeout: float):
        self.server = server
        self._connect_timeout = connect_timeout
        self._observation = TransportObservation()
        self._owner: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[list[McpToolInfo]] | None = None
        self._stop = asyncio.Event()
        self._client: Client | None = None
        self._terminal: Exception | None = None
        self._cleanup_error: Exception | None = None

    async def connect(self) -> list[McpToolInfo]:
        """Discover all pages before publishing; only readiness has a connection deadline."""
        if self._owner is not None:
            raise McpProtocolError("MCP 会话已启动")
        self._ready = asyncio.get_running_loop().create_future()
        self._owner = asyncio.create_task(self._run(), name=f"mcp:{self.server}")
        try:
            return await asyncio.wait_for(
                asyncio.shield(self._ready), self._connect_timeout
            )
        except BaseException:
            await self.disconnect()
            raise

    async def _run(self) -> None:
        _diagnostics_acquire()
        diagnostic_token = _DIAGNOSTICS.set(True)
        status: list[int] = []
        status_token = _HTTP_STATUS.set(status)
        try:
            async with Client(
                self._observed_transport(),
                read_timeout_seconds=None,
                cache=None,
            ) as client:
                infos = []
                cursor = None
                cursors: set[str] = set()
                while True:
                    page = await client.list_tools(cursor=cursor)
                    infos.extend(
                        McpToolInfo(
                            tool.name, tool.description or "", tool.input_schema
                        )
                        for tool in page.tools
                    )
                    cursor = page.next_cursor
                    if cursor is None:
                        break
                    if cursor in cursors:
                        raise McpProtocolError("MCP 工具发现失败：分页游标重复")
                    cursors.add(cursor)
                self._client = client
                if self._ready is not None and not self._ready.done():
                    self._ready.set_result(infos)
                await self._stop.wait()
        except BaseException as error:
            self._terminal = _failure(error, status, "连接")
            if self._ready is not None and not self._ready.done():
                self._ready.set_exception(self._terminal)
        finally:
            self._client = None
            _HTTP_STATUS.reset(status_token)
            _DIAGNOSTICS.reset(diagnostic_token)
            _diagnostics_release()

    def _transport(self) -> Transport:
        raise NotImplementedError

    @staticmethod
    def _result_payload(result: CallToolResult) -> dict[str, Any]:
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)

    @asynccontextmanager
    async def _observed_transport(self):
        async with self._transport() as streams:
            yield self._observation.streams(streams)

    async def call(
        self, tool_name: str, arguments: dict[str, Any], *, timeout: float | None = None
    ) -> str | ToolResult:
        """Call once; preserve per-source deadlines and refuse unsupported input requests."""
        if self._client is None or self._stop.is_set():
            raise self._terminal or ConnectionError("MCP 会话已断开")
        observation = CallObservation()
        call_token = CURRENT_CALL.set(observation)
        status: list[int] = []
        status_token = _HTTP_STATUS.set(status)
        diagnostic_token = _DIAGNOSTICS.set(True)
        try:
            deadline = 30.0 if timeout is None else timeout
            # The outer deadline includes the send queue. Keep the SDK read
            # timer disabled: its local timeout code overlaps remote RPC errors.
            # Cancellation still awaits its bounded courtesy-notification cleanup.
            async with asyncio.timeout(deadline):
                result = await self._client.session.call_tool(
                    tool_name,
                    arguments,
                    read_timeout_seconds=None,
                    allow_input_required=False,
                    allow_claimed=False,
                )
            return decode_tool_result(
                self.server, tool_name, {"result": self._result_payload(result)}
            )
        except MCPError as error:
            if status and status[-1] >= 400:
                raise _failure(error, status, "调用") from None
            if (
                self._observation.failed or self._stop.is_set()
            ) and not observation.received_error:
                raise ConnectionError("MCP 调用连接已断开") from None
            raise McpToolError(
                server=self.server,
                tool_name=tool_name,
                message=error.message,
                code=error.code,
                data=error.data,
            ) from None
        except McpToolError:
            raise
        except Exception as error:
            raise _failure(error, status, "调用") from None
        finally:
            self._observation.release(observation)
            CURRENT_CALL.reset(call_token)
            _DIAGNOSTICS.reset(diagnostic_token)
            _HTTP_STATUS.reset(status_token)

    async def disconnect(self) -> None:
        """The owner exits both SDK contexts in its own task, including failed connects."""
        self._stop.set()
        owner = self._owner
        if owner is None:
            return
        if self._ready is not None and not self._ready.done():
            owner.cancel()
        await asyncio.shield(owner)
        if (
            self._ready is not None
            and self._ready.done()
            and not self._ready.cancelled()
        ):
            self._ready.exception()
        if self._cleanup_error is not None:
            raise self._cleanup_error
