"""Owns one stdio MCP connection with a single reader and correlated requests."""

import asyncio
import json
import logging
import os
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.mcp.result import McpToolError as McpToolError, decode_tool_result
from agent.mcp.windows_job import WindowsJob
from agent.tools.base import ToolResult

logger = logging.getLogger(__name__)
_RECV_TIMEOUT = 30.0
_CONNECT_TIMEOUT = 8.0
# agent-browser permits 10 MiB images; allow base64 plus JSON and text metadata.
_STREAM_LIMIT = 20 * 1024 * 1024


@dataclass
class McpToolInfo:
    """A discovered remote tool schema."""

    name: str
    description: str
    input_schema: dict[str, Any]


def _infer_cwd(command: list[str]) -> str | None:
    for arg in command:
        p = Path(arg)
        if p.is_absolute() and p.is_file():
            return str(p.parent)
    return None


class McpClient:
    """One MCP process, response dispatcher and explicit connection lifetime."""

    def __init__(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        *,
        own_process_tree: bool = False,
        inherit_env: bool = True,
    ) -> None:
        self.name, self.command = name, command
        self.env = env or {}
        self.cwd = cwd or _infer_cwd(command)
        self._own_process_tree = own_process_tree
        self._inherit_env = inherit_env
        self._job: WindowsJob | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._read_error: Exception | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._write_lock = asyncio.Lock()
        self._disconnect_lock = asyncio.Lock()
        self._next_id = 1
        self._tool_infos: list[McpToolInfo] = []
        self._recent_stdout: deque[str] = deque(maxlen=8)
        self._recent_stderr: deque[str] = deque(maxlen=8)

    @property
    def tool_infos(self) -> list[McpToolInfo]:
        """Returns the schemas discovered by this connection."""
        return self._tool_infos

    async def connect(self) -> list[McpToolInfo]:
        """Starts the server and discovers all pages of tools; failure closes it."""
        if self._process is not None:
            raise RuntimeError(f"MCP client {self.name!r} is already connected")
        try:
            return await asyncio.wait_for(self._connect_impl(), _CONNECT_TIMEOUT)
        except BaseException:
            await self.disconnect()
            raise

    async def _connect_impl(self) -> list[McpToolInfo]:
        self._read_error = None
        self._process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.env} if self._inherit_env else self.env,
            cwd=self.cwd,
            limit=_STREAM_LIMIT,
            creationflags=0x08000004 if self._own_process_tree else 0,
        )
        if self._own_process_tree:
            self._job = WindowsJob(self._process.pid, resume=True)
        if self._process.stdout is None or self._process.stderr is None:
            raise RuntimeError("MCP stdout/stderr unavailable")
        self._stderr_task = asyncio.create_task(
            self._drain_stderr(self._process.stderr)
        )
        self._reader_task = asyncio.create_task(
            self._read_responses(self._process.stdout)
        )
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "shiori-agent", "version": "1.0"},
            },
        )
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._tool_infos = []
        params: dict[str, Any] = {}
        cursors: set[str] = set()
        while True:
            response = await self._request("tools/list", params)
            result = response["result"]
            self._tool_infos.extend(
                McpToolInfo(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get(
                        "inputSchema", {"type": "object", "properties": {}}
                    ),
                )
                for t in result.get("tools", [])
            )
            cursor = result.get("nextCursor")
            if not cursor:
                break
            if cursor in cursors:
                raise RuntimeError("MCP tools/list repeated a pagination cursor")
            cursors.add(cursor)
            params = {"cursor": cursor}
        return self._tool_infos

    async def call(
        self, tool_name: str, arguments: dict[str, Any], *, timeout: float | None = None
    ) -> str | ToolResult:
        """Returns text or original images; protocol/tool errors propagate."""
        response = await self._request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            timeout=timeout,
            tool_name=tool_name,
        )
        return decode_tool_result(self.name, tool_name, response)

    async def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float | None = None,
        tool_name: str | None = None,
    ) -> dict[str, Any]:
        if self._read_error is not None:
            raise ConnectionError(
                f"MCP connection {self.name!r} failed"
            ) from self._read_error
        call_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[call_id] = future
        deadline = _RECV_TIMEOUT if timeout is None else timeout
        try:
            async with asyncio.timeout(deadline):
                await self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": call_id,
                        "method": method,
                        "params": params,
                    }
                )
                response = await future
            if "error" in response:
                decode_tool_result(self.name, tool_name or method, response)
            return response
        except (asyncio.CancelledError, TimeoutError) as exc:
            # Late responses have no pending recipient; never recycle request ids.
            # Cancellation is advisory at this transport boundary and must never
            # block teardown behind a peer that stopped reading stdin.
            with suppress(ConnectionError, BrokenPipeError, RuntimeError, TimeoutError):
                async with asyncio.timeout(0.2):
                    await self._send(
                        {
                            "jsonrpc": "2.0",
                            "method": "notifications/cancelled",
                            "params": {
                                "requestId": call_id,
                                "reason": "Request stopped",
                            },
                        }
                    )
            if isinstance(exc, TimeoutError):
                raise TimeoutError(
                    self._build_timeout_message(method, call_id, deadline)
                ) from exc
            raise
        finally:
            self._pending.pop(call_id, None)
            if not future.done():
                future.cancel()

    async def _read_responses(self, stdout: asyncio.StreamReader) -> None:
        try:
            while True:
                line = await stdout.readline()
                if not line:
                    raise ConnectionError(f"MCP server {self.name!r} 意外关闭了 stdout")
                text = line.decode().strip()
                try:
                    response = json.loads(text)
                except json.JSONDecodeError:
                    self._recent_stdout.append(text[:500])
                    continue
                if not isinstance(response, dict):
                    continue
                # Diagnostics retain envelope metadata, never image bytes.
                self._recent_stdout.append(
                    f"id={response.get('id')!r} method={response.get('method')!r}"
                )
                if "method" in response:
                    continue
                response_id = response.get("id")
                if not isinstance(response_id, int):
                    continue
                future = self._pending.get(response_id)
                if future is not None and not future.done():
                    future.set_result(response)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._read_error = exc
            self._fail_pending(exc)

    def _fail_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)

    async def _send(self, payload: dict[str, Any]) -> None:
        async with self._write_lock:
            if (
                self._process is None
                or self._process.stdin is None
                or self._process.returncode is not None
            ):
                raise ConnectionError(f"MCP client {self.name!r} 未连接")
            self._process.stdin.write(
                (json.dumps(payload, ensure_ascii=False) + "\n").encode()
            )
            await self._process.stdin.drain()

    async def disconnect(self) -> None:
        """Closes the owned process tree and drains protocol tasks before returning."""
        async with self._disconnect_lock:
            self._fail_pending(
                ConnectionError(f"MCP client {self.name!r} disconnected")
            )
            process, self._process = self._process, None
            errors: list[Exception] = []
            if self._job is not None:
                try:
                    self._job.close()
                except Exception as exc:
                    errors.append(exc)
                finally:
                    self._job = None
            try:
                if process is not None:
                    if process.returncode is None:
                        with suppress(ProcessLookupError):
                            process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 5)
                    except TimeoutError:
                        with suppress(ProcessLookupError):
                            process.kill()
                        await asyncio.wait_for(process.wait(), 5)
            except Exception as exc:
                errors.append(exc)
            finally:
                for task in (self._reader_task, self._stderr_task):
                    if task is not None:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                self._reader_task = self._stderr_task = None
                self._tool_infos = []
            if len(errors) == 1:
                raise errors[0]
            if errors:
                raise ExceptionGroup("MCP cleanup failed", errors)

    async def _drain_stderr(self, stderr: asyncio.StreamReader) -> None:
        """后台读取 stderr，防止缓冲区阻塞。

        流由 `_connect_impl` 取好后传入，因此"流不可用"在连接时就已失败。
        子进程的 stderr 未必是合法 UTF-8，解码用 replace 兜底：这个协程的
        全部职责就是持续排空，不能因为一个坏字节停下来让管道写满。
        """
        try:
            while True:
                line = await stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                self._recent_stderr.append(text[:500])
                logger.debug("[mcp:%s] stderr: %s", self.name, text)
        except Exception as e:
            # 排空失败不影响 stdio 主协议通道，因此在这里就地记录并结束，
            # 而不是把异常留给一个无人 await 的 task 在 GC 时才暴露。
            logger.warning("[mcp:%s] stderr 排空中止: %s", self.name, e)

    def _build_timeout_message(
        self,
        stage: str,
        expected_id: int | None,
        timeout: float,
    ) -> str:
        details = [
            f"MCP server {self.name!r} 在阶段 {stage!r} 等待响应超时（{timeout:.0f}s）",
        ]
        if expected_id is not None:
            details.append(f"expected_id={expected_id}")
        if self.command:
            details.append(f"command={self.command!r}")
        if self.cwd:
            details.append(f"cwd={self.cwd}")
        if self._recent_stdout:
            details.append("recent_stdout=" + " | ".join(self._recent_stdout))
        if self._recent_stderr:
            details.append("recent_stderr=" + " | ".join(self._recent_stderr))
        return "; ".join(details)
