"""Shell 子进程启动、等待与进程树终止。"""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any, Callable

from .constants import _IS_WINDOWS, _STREAM_DRAIN_GRACE_S
from .output import _read_output


async def _start_process(
    command: str, *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> asyncio.subprocess.Process:
    """使用平台对应 shell 启动命令；Windows 明确要求 PowerShell 7。"""
    options = _subprocess_options(cwd, env)
    if not _IS_WINDOWS:
        return await asyncio.create_subprocess_shell(command, **options)

    executable = shutil.which("pwsh", path=env.get("PATH") if env is not None else None)
    if executable is None:
        raise FileNotFoundError(
            "Windows shell 需要 PowerShell 7：请安装 pwsh 并加入 PATH"
        )
    # 编码传参避免 Windows argv 再次解释引号；不追加命令以保留 $? / exit 语义。
    script = (
        "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "$OutputEncoding = [Console]::OutputEncoding\n" + command
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return await asyncio.create_subprocess_exec(
        executable,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-OutputFormat",
        "Text",
        "-EncodedCommand",
        encoded,
        **options,
    )


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
    proc = await _start_process(command, cwd=cwd, env=env)

    def _kill_tree() -> None:
        """杀掉整棵进程树（按 pgid）。"""
        try:
            _invoke_kill_process_tree(proc)
        except (ProcessLookupError, PermissionError):
            pass  # 进程已退出或无权限

    async def _pump(stream, chunks: list[str]) -> None:
        async for text in _read_output(stream):
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
        await _wait_proc()
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
        await _wait_proc()
        raise
