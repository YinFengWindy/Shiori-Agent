"""Chunked MCP pipes using the caller's generic process ownership primitive."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import anyio
from mcp.client._transport import Transport, TransportStreams
from mcp.shared.message import SessionMessage
from mcp_types import jsonrpc_message_adapter
from shiori_sdk.processes import Processes

from .session import ClientSession

_MAX_FRAME = 20 * 1024 * 1024
_LOG = logging.getLogger(__name__)


def _infer_cwd(command: list[str]) -> str:
    for argument in command:
        path = Path(argument)
        if path.is_absolute() and path.is_file():
            return str(path.parent)
    return os.getcwd()


class StdioMcpSession(ClientSession):
    """One official MCP client over host-owned pipes and an explicit environment."""

    def __init__(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        *,
        processes: Processes,
        own_process_tree: bool = False,
        inherit_env: bool = True,
        connect_timeout: float = 8.0,
    ):
        super().__init__(name, connect_timeout=connect_timeout)
        self.command, self.env, self.cwd = list(command), dict(env or {}), cwd
        self._processes = processes
        self.own_process_tree, self.inherit_env = own_process_tree, inherit_env

    def _transport(self) -> Transport:
        return self._pipes()

    @asynccontextmanager
    async def _pipes(self) -> AsyncIterator[TransportStreams]:
        process, owner = await self._processes.spawn(
            *self.command,
            env=({**os.environ, **self.env} if self.inherit_env else dict(self.env)),
            cwd=self.cwd or _infer_cwd(self.command),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            own_process_tree=self.own_process_tree,
        )
        # No await between successful spawn and installing its cleanup owner.
        read_send, read_receive = anyio.create_memory_object_stream[
            SessionMessage | Exception
        ](0)
        write_send, write_receive = anyio.create_memory_object_stream[SessionMessage](0)
        tasks: list[asyncio.Task[None]] = []

        async def read_stdout() -> None:
            assert process.stdout is not None
            buffer = bytearray()
            async with read_send:
                try:
                    while chunk := await process.stdout.read(64 * 1024):
                        buffer.extend(chunk)
                        while (newline := buffer.find(b"\n")) >= 0:
                            if newline > _MAX_FRAME:
                                raise ValueError("MCP frame exceeds 20 MiB")
                            line = bytes(buffer[:newline])
                            del buffer[: newline + 1]
                            # Official parsing owns JSON-RPC validation; raw wire
                            # failures never enter logs or cross this boundary.
                            try:
                                message = jsonrpc_message_adapter.validate_json(
                                    line, by_name=False
                                )
                            except ValueError:
                                raise ValueError("Invalid MCP JSON-RPC frame") from None
                            await read_send.send(SessionMessage(message))
                        if len(buffer) > _MAX_FRAME:
                            raise ValueError("MCP frame exceeds 20 MiB")
                    if buffer:
                        raise ValueError("Truncated MCP JSON-RPC frame")
                except Exception:
                    with suppress(anyio.BrokenResourceError, anyio.ClosedResourceError):
                        await read_send.send(ConnectionError("MCP stdio stream ended"))

        async def write_stdin() -> None:
            assert process.stdin is not None
            try:
                async with write_receive:
                    async for message in write_receive:
                        wire = message.message.model_dump_json(
                            by_alias=True, exclude_unset=True
                        )
                        process.stdin.write((wire + "\n").encode("utf-8"))
                        await process.stdin.drain()
            except (OSError, anyio.BrokenResourceError, anyio.ClosedResourceError):
                # Closing the inbound stream fails pending requests promptly even
                # when a broken stdin belongs to a server still holding stdout.
                await read_send.aclose()

        async def drain_stderr() -> None:
            assert process.stderr is not None
            while chunk := await process.stderr.read(64 * 1024):
                _LOG.debug("MCP stderr (%d bytes)", len(chunk))

        async def cleanup() -> None:
            errors: list[Exception] = []
            await write_send.aclose()
            if process.stdin is not None:
                process.stdin.close()
            if owner is not None:
                try:
                    owner.close()
                except Exception as error:
                    errors.append(error)
            try:
                if process.returncode is None:
                    with suppress(ProcessLookupError):
                        process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5.0)
                except TimeoutError:
                    with suppress(ProcessLookupError):
                        process.kill()
                    await asyncio.wait_for(process.wait(), 5.0)
            except Exception as error:
                errors.append(error)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await read_receive.aclose()
                await read_send.aclose()
                await write_receive.aclose()
            if errors:
                self._cleanup_error = RuntimeError("MCP process cleanup failed")
                raise self._cleanup_error

        try:
            tasks.extend(
                asyncio.create_task(operation(), name=f"mcp-pipe:{self.server}:{name}")
                for name, operation in (
                    ("stdout", read_stdout),
                    ("stdin", write_stdin),
                    ("stderr", drain_stderr),
                )
            )
            yield read_receive, write_send
        finally:
            # SDK cancellation scopes and external task cancellation must both
            # leave the process reaped before this context has finished exiting.
            with anyio.CancelScope(shield=True):
                closing = asyncio.create_task(cleanup())
                try:
                    await asyncio.shield(closing)
                except asyncio.CancelledError:
                    await closing
                    raise
