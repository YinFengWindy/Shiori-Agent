from __future__ import annotations

import asyncio

import pytest

from coding_agents.adapters.process import AsyncioManagedProcess


class _HungProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.stdout = None
        self.stderr = None
        self.pid = 987654
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        if self.killed:
            return -9
        await asyncio.Event().wait()
        return 0


@pytest.mark.asyncio
async def test_stop_terminates_the_entire_windows_process_tree(monkeypatch) -> None:
    process = _HungProcess()
    managed = AsyncioManagedProcess(process)  # type: ignore[arg-type]

    class _Taskkill:
        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        assert args[:4] == ("taskkill.exe", "/PID", "987654", "/T")
        return _Taskkill()

    monkeypatch.setattr(
        "coding_agents.adapters.process.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    await managed.stop(grace_seconds=0.001)

    assert process.terminated is False
    assert process.killed is True
