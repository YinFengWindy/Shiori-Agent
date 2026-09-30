"""Spawns child processes whose whole tree dies with the host on Windows."""

import asyncio
import os
import subprocess
from collections.abc import Mapping
from typing import IO, Any

from infra.process.windows_job import WindowsJob

CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
# Suspended until the job owns it, so no descendant can escape before assignment.
OWNED_TREE_FLAGS = CREATE_NO_WINDOW | CREATE_SUSPENDED


async def spawn_owned(
    *command: str, owned: bool = True, **kwargs: Any
) -> tuple[asyncio.subprocess.Process, WindowsJob | None]:
    """Starts an asyncio subprocess, adopting its tree into a kill-on-close job.

    With ``owned=False`` the process starts normally and no job is returned.
    If the job cannot be created the suspended child is killed and reaped
    before the error propagates.
    """
    process = await asyncio.create_subprocess_exec(
        *command, creationflags=OWNED_TREE_FLAGS if owned else 0, **kwargs
    )
    if not owned:
        return process, None
    try:
        return process, WindowsJob(process.pid, resume=True)
    except BaseException:
        process.kill()
        await process.wait()
        raise


def popen_owned(
    command: list[str],
    *,
    owned: bool = True,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    stdout: int | IO[Any] | None = None,
    stderr: int | IO[Any] | None = None,
) -> tuple[subprocess.Popen[bytes], WindowsJob | None]:
    """Blocking ``subprocess.Popen`` counterpart of :func:`spawn_owned`."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=stdout,
        stderr=stderr,
        creationflags=OWNED_TREE_FLAGS if owned else 0,
    )
    if not owned:
        return process, None
    try:
        return process, WindowsJob(process.pid, resume=True)
    except BaseException:
        process.kill()
        process.wait()
        raise
