from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path

from coding_agents.adapters.process import CapturedProcess


class FakeProcess:
    def __init__(
        self,
        *,
        stdout: Sequence[bytes] = (),
        stderr: Sequence[bytes] = (),
        exit_code: int = 0,
        block: bool = False,
    ) -> None:
        self._stdout = tuple(stdout)
        self._stderr = tuple(stderr)
        self._exit_code = exit_code
        self._block = block
        self.stopped = False

    async def stdout_lines(self) -> AsyncIterator[bytes]:
        for line in self._stdout:
            yield line
        if self._block and not self.stopped:
            await asyncio.Event().wait()

    async def stderr_lines(self) -> AsyncIterator[bytes]:
        for line in self._stderr:
            yield line

    async def wait(self) -> int:
        if self._block and not self.stopped:
            await asyncio.Event().wait()
        return -9 if self.stopped else self._exit_code

    async def stop(self, grace_seconds: float = 3.0) -> None:
        self.stopped = True


class FakeProcessRunner:
    def __init__(
        self,
        process: FakeProcess | None = None,
        captures: Sequence[CapturedProcess | Exception] = (),
        start_error: Exception | None = None,
    ) -> None:
        self.process = process or FakeProcess()
        self.captures = list(captures)
        self.start_error = start_error
        self.started: list[
            tuple[tuple[str, ...], Path, Mapping[str, str], bytes]
        ] = []
        self.probed: list[tuple[str, ...]] = []

    async def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        stdin: bytes,
    ) -> FakeProcess:
        if self.start_error is not None:
            raise self.start_error
        self.started.append((tuple(command), cwd, environment, stdin))
        return self.process

    async def capture(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> CapturedProcess:
        self.probed.append(tuple(command))
        outcome = self.captures.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
