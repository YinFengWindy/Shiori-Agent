"""Shell 子进程启动、等待与进程树终止。"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Callable

from .constants import _IS_WINDOWS, _STREAM_CHUNK_SIZE, _STREAM_DRAIN_GRACE_S


def _subprocess_options(cwd: Path | None, env: dict[str, str] | None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "cwd": str(cwd) if cwd is not None else None,
        "env": env,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if _IS_WINDOWS:
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return options


def _kill_process_tree(proc: Any) -> None:
    if _IS_WINDOWS:
        result = subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            proc.kill()
        return
    os.killpg(proc.pid, signal.SIGKILL)


def _invoke_kill_process_tree(proc: Any) -> None:
    """调用 facade 当前暴露的终止 hook，保留测试与调用方 monkeypatch 语义。"""

    from agent.tools import shell as shell_facade

    hook = getattr(shell_facade, "_kill_process_tree", _kill_process_tree)
    hook(proc)


async def _run(
    command: str,
    timeout: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    on_data: Callable[[str], None] | None = None,
) -> tuple[str, str, int, bool]:
    """执行命令，并发读取 stdout/stderr，返回 (stdout, stderr, exit_code, interrupted)"""
    proc = await asyncio.create_subprocess_shell(
        command,
        **_subprocess_options(cwd, env),
    )

    def _kill_tree() -> None:
        """杀掉整棵进程树（按 pgid）。"""
        try:
            _invoke_kill_process_tree(proc)
        except (ProcessLookupError, PermissionError):
            pass  # 进程已退出或无权限

    async def _pump(stream, chunks: list[str]) -> None:
        if stream is None:
            return
        while True:
            data = await stream.read(_STREAM_CHUNK_SIZE)
            if not data:
                break
            text = data.decode(errors="replace")
            chunks.append(text)
            if on_data is not None:
                on_data(text)

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_task = asyncio.create_task(_pump(proc.stdout, stdout_chunks))
    stderr_task = asyncio.create_task(_pump(proc.stderr, stderr_chunks))

    async def _finish_pumps() -> None:
        try:
            await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task),
                timeout=_STREAM_DRAIN_GRACE_S,
            )
        except asyncio.TimeoutError:
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

    async def _wait_proc() -> int:
        if hasattr(proc, "wait"):
            return await proc.wait()
        await proc.communicate()
        return proc.returncode or 0

    try:
        await asyncio.wait_for(_wait_proc(), timeout=timeout)
        await _finish_pumps()
        return (
            "".join(stdout_chunks),
            "".join(stderr_chunks),
            proc.returncode or 0,
            False,
        )
    except asyncio.TimeoutError:
        _kill_tree()
        await _finish_pumps()
        return (
            "".join(stdout_chunks),
            "".join(stderr_chunks),
            -1,
            True,
        )
    except asyncio.CancelledError:
        _kill_tree()
        stdout_task.cancel()
        stderr_task.cancel()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise
