"""Official MCP HTTP transport, with one task owning its entire context lifetime."""

from __future__ import annotations

import asyncio
import json
import logging
from contextvars import ContextVar
from typing import Any

import anyio
import httpx2
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CONNECTION_CLOSED, REQUEST_TIMEOUT, CallToolResult
from shiori_sdk.mcp import McpToolError, McpToolInfo
from shiori_sdk.mcp_result import decode_tool_result
from shiori_sdk.tools import ToolResult

from .models import HttpTransport, LaunchCredentials, McpConfigError, McpHttpError

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
            record.msg = "MCP HTTP transport diagnostic"
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
    if status and status[-1] in {401, 403}:
        message = "认证未通过" if status[-1] == 401 else "访问被拒绝"
        return McpHttpError(f"MCP HTTP {phase}失败（{status[-1]}）：{message}")
    if isinstance(error, BaseExceptionGroup):
        failures = [_failure(item, status, phase) for item in error.exceptions]
        return next(
            (item for item in failures if isinstance(item, ConnectionError)),
            failures[0],
        )
    if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
        return TimeoutError(f"MCP HTTP {phase}超时")
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
        return ConnectionError(f"MCP HTTP {phase}连接已断开")
    if isinstance(error, MCPError) and error.code == CONNECTION_CLOSED:
        return ConnectionError(f"MCP HTTP {phase}连接已断开")
    if status and status[-1] >= 400:
        return McpHttpError(f"MCP HTTP {phase}失败（{status[-1]}）")
    if isinstance(error, McpConfigError):
        return error
    return McpConfigError(f"MCP HTTP {phase}失败：响应不符合协议")


def _result_payload(result: CallToolResult) -> dict[str, Any]:
    """Preserve modern JSON values as text without changing ToolResult's object contract."""
    payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    if "structured_content" in result.model_fields_set and not isinstance(
        result.structured_content, dict
    ):
        value = result.structured_content
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        content = payload.setdefault("content", [])
        equivalent = False
        for block in content:
            if block.get("type") == "text":
                try:
                    # Compare JSON representations, so True and 1 remain different.
                    equivalent = (
                        json.dumps(
                            json.loads(block["text"]),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        == text
                    )
                except (ValueError, TypeError, KeyError):
                    continue
                if equivalent:
                    break
        if not equivalent:
            content.append({"type": "text", "text": text})
        payload.pop("structuredContent", None)
    return payload


class HttpMcpSession:
    """A single eager HTTP connection; calls never connect or replay themselves."""

    def __init__(
        self, server: str, transport: HttpTransport, credentials: LaunchCredentials
    ):
        self.server = server
        self._url = credentials.url or ""
        self._headers = dict(credentials.headers)
        if transport.auth == "bearer":
            self._headers["Authorization"] = f"Bearer {credentials.bearer}"
        self._owner: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[list[McpToolInfo]] | None = None
        self._stop = asyncio.Event()
        self._client: Client | None = None
        self._terminal: Exception | None = None

    async def connect(self) -> list[McpToolInfo]:
        """Discover all pages before publishing; only readiness has a connection deadline."""
        if self._owner is not None:
            raise McpConfigError("MCP HTTP 会话已启动")
        self._ready = asyncio.get_running_loop().create_future()
        self._owner = asyncio.create_task(self._run(), name=f"mcp-http:{self.server}")
        try:
            return await asyncio.wait_for(asyncio.shield(self._ready), 15.0)
        except BaseException:
            await self.disconnect()
            raise

    async def _run(self) -> None:
        _diagnostics_acquire()
        diagnostic_token = _DIAGNOSTICS.set(True)
        status: list[int] = []
        status_token = _HTTP_STATUS.set(status)
        try:
            async with httpx2.AsyncClient(
                headers=self._headers,
                timeout=httpx2.Timeout(15.0, read=300.0),
                follow_redirects=False,
                event_hooks={"request": [self._request], "response": [self._response]},
            ) as http:
                async with Client(
                    streamable_http_client(
                        self._url, http_client=http, max_sse_event_size=20 * 1024 * 1024
                    ),
                    read_timeout_seconds=30.0,
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
                            raise McpConfigError("MCP HTTP 工具发现失败：分页游标重复")
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

    @staticmethod
    async def _request(request: httpx2.Request) -> None:
        if request.method == "DELETE":
            request.extensions["timeout"] = httpx2.Timeout(2.0).as_dict()

    @staticmethod
    async def _response(response: httpx2.Response) -> None:
        statuses = _HTTP_STATUS.get()
        if statuses is not None:
            statuses.append(response.status_code)

    async def call(
        self, tool_name: str, arguments: dict[str, Any], *, timeout: float | None = None
    ) -> str | ToolResult:
        """Call once; preserve per-source deadlines and refuse unsupported input requests."""
        if self._client is None or self._stop.is_set():
            raise self._terminal or ConnectionError("MCP HTTP 会话已断开")
        status: list[int] = []
        status_token = _HTTP_STATUS.set(status)
        diagnostic_token = _DIAGNOSTICS.set(True)
        try:
            deadline = 30.0 if timeout is None else timeout
            # The SDK's read timer starts after its send queue accepts the
            # request. Cover that wait too; cancellation removes the queued
            # call, then awaits the SDK's bounded courtesy-notification cleanup.
            async with asyncio.timeout(deadline):
                result = await self._client.session.call_tool(
                    tool_name,
                    arguments,
                    read_timeout_seconds=deadline,
                    allow_input_required=False,
                    allow_claimed=False,
                )
            return decode_tool_result(
                self.server, tool_name, {"result": _result_payload(result)}
            )
        except MCPError as error:
            if error.code == REQUEST_TIMEOUT:
                raise TimeoutError("MCP HTTP 工具调用超时") from None
            if (status and status[-1] >= 400) or error.code == CONNECTION_CLOSED:
                raise _failure(error, status, "调用") from None
            raise McpToolError(
                server=self.server,
                tool_name=tool_name,
                message="MCP HTTP 工具返回协议错误",
                code=error.code,
            ) from None
        except McpToolError:
            raise
        except Exception as error:
            raise _failure(error, status, "调用") from None
        finally:
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
