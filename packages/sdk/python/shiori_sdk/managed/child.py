"""A plugin-owned child tree, always released through the injected native owner."""

import asyncio
import os
from pathlib import Path
from typing import BinaryIO

from shiori_sdk.processes import ProcessOwner, Processes
from .paths import environment_path, native_path


def private_environment(
    root: Path,
    executables: Path,
    *,
    cache_variables: tuple[str, ...] = (),
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Isolate Python/temp files and provider-selected cache variables from the host."""
    root, executables = native_path(root), native_path(executables)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "VIRTUAL_ENV", "CONDA"))
    }
    temporary = root / "tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    env.update(
        PATH=environment_path(executables) + os.pathsep + env.get("PATH", ""),
        PYTHONNOUSERSITE="1",
        TEMP=environment_path(temporary),
        TMP=environment_path(temporary),
    )
    # Third-party archive libraries may append POSIX member names. Extended
    # namespaces disable Win32 slash normalization and would turn that into Win123.
    env.update(
        {
            name: environment_path(root / "cache" / name.lower())
            for name in cache_variables
        }
    )
    env.update(overrides or {})
    return env


class OwnedChild:
    """No PID adoption: only the native owner returned for this spawn may be closed."""

    def __init__(self, processes: Processes):
        self.processes = processes
        self.process: asyncio.subprocess.Process | None = None
        self.owner: ProcessOwner | None = None
        self.log: BinaryIO | None = None

    async def start(
        self, command: list[str], *, cwd: Path, env: dict[str, str], log: Path
    ) -> None:
        """Launch a hidden tree with output retained in private plugin data."""
        if self.process is not None:
            raise RuntimeError("进程已启动")
        # Preserve the caller's executable/cwd spelling. Third-party Python code
        # may require normal sys.prefix semantics for relative DLL/script paths.
        log = native_path(log)
        log.parent.mkdir(parents=True, exist_ok=True)
        self.log = log.open("ab")
        try:
            self.process, self.owner = await self.processes.spawn(
                *command,
                env=env,
                cwd=str(cwd),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=self.log,
                stderr=self.log,
            )
        except BaseException:
            self.log.close()
            self.log = None
            raise

    async def close(self) -> None:
        """Kill the owned tree and join the child before releasing file handles."""
        process, owner = self.process, self.owner
        if owner is not None:
            owner.close()
        elif process is not None and process.returncode is None:
            process.kill()
        if process is not None:
            await process.wait()
        # Preserve handles on close/wait failure: another owner must not replace
        # a tree whose termination has not actually been observed.
        self.process = self.owner = None
        if self.log is not None:
            self.log.close()
            self.log = None


async def run_owned(
    processes: Processes,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
) -> None:
    """Run one preparation command; cancellation kills and joins its complete tree."""
    child = OwnedChild(processes)
    try:
        await child.start(command, cwd=cwd, env=env, log=log)
        assert child.process is not None
        code = await child.process.wait()
        if code:
            raise RuntimeError(f"环境准备命令失败（{code}），详见 {log}")
    finally:
        await child.close()
