"""可注入的异步子进程边界。"""

from __future__ import annotations

import asyncio
import os
import signal
import shutil
import subprocess
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_IS_WINDOWS = os.name == "nt"


def _resolve_command(command: Sequence[str]) -> tuple[str, ...]:
    if not command:
        raise ValueError("进程命令不能为空")
    if not _IS_WINDOWS:
        return tuple(command)
    executable = shutil.which(command[0])
    return (executable or command[0], *command[1:])


@dataclass(frozen=True)
class CapturedProcess:
    """短命令执行结果，主要用于 CLI 能力探测。"""

    exit_code: int
    stdout: str
    stderr: str


class ManagedProcess(Protocol):
    """可流式读取且可终止的进程句柄。"""

    def stdout_lines(self) -> AsyncIterator[bytes]: ...

    def stderr_lines(self) -> AsyncIterator[bytes]: ...

    async def wait(self) -> int: ...

    async def stop(self, grace_seconds: float = 3.0) -> None: ...


class ProcessRunner(Protocol):
    """进程创建接口，可由单元测试替换为 Fake。"""

    async def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        stdin: bytes,
    ) -> ManagedProcess: ...

    async def capture(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> CapturedProcess: ...


class AsyncioManagedProcess:
    """封装 asyncio Process，保证取消时终止受管进程。"""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process

    async def _lines(
        self, reader: asyncio.StreamReader | None
    ) -> AsyncIterator[bytes]:
        if reader is None:
            return
        while line := await reader.readline():
            yield line

    def stdout_lines(self) -> AsyncIterator[bytes]:
        return self._lines(self._process.stdout)

    def stderr_lines(self) -> AsyncIterator[bytes]:
        return self._lines(self._process.stderr)

    async def wait(self) -> int:
        return await self._process.wait()

    async def stop(self, grace_seconds: float = 3.0) -> None:
        if self._process.returncode is not None:
            return
        if os.name == "nt":
            await self._kill_tree()
            await self._process.wait()
            return
        self._terminate_tree()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=grace_seconds)
        except asyncio.TimeoutError:
            await self._kill_tree()
            await self._process.wait()

    def _terminate_tree(self) -> None:
        try:
            os.killpg(self._process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

    async def _kill_tree(self) -> None:
        if os.name == "nt":
            taskkill = await asyncio.create_subprocess_exec(
                "taskkill.exe",
                "/PID",
                str(self._process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await taskkill.wait()
            if self._process.returncode is None:
                self._process.kill()
            return
        try:
            os.killpg(self._process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return


class AsyncioProcessRunner:
    """生产环境 asyncio 子进程实现。"""

    async def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        stdin: bytes,
    ) -> ManagedProcess:
        resolved_command = _resolve_command(command)
        if os.name == "nt":
            process = await asyncio.create_subprocess_exec(
                *resolved_command,
                cwd=str(cwd),
                env=dict(environment),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *resolved_command,
                cwd=str(cwd),
                env=dict(environment),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        assert process.stdin is not None
        process.stdin.write(stdin)
        await process.stdin.drain()
        process.stdin.close()
        return AsyncioManagedProcess(process)

    async def capture(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> CapturedProcess:
        resolved_command = _resolve_command(command)
        process = await asyncio.create_subprocess_exec(
            *resolved_command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise
        return CapturedProcess(
            exit_code=process.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
