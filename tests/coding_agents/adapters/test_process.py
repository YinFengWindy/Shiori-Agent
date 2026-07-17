from __future__ import annotations

import asyncio

import pytest

from coding_agents.adapters.process import AsyncioManagedProcess, _resolve_command


def test_resolve_command_uses_windows_cli_shim_path(monkeypatch) -> None:
    monkeypatch.setattr("coding_agents.adapters.process._IS_WINDOWS", True)
    monkeypatch.setattr(
        "coding_agents.adapters.process.shutil.which",
        lambda executable: f"C:/npm/{executable}.cmd",
    )

    assert _resolve_command(("codex", "--version")) == (
        "C:/npm/codex.cmd",
        "--version",
    )


def test_resolve_command_preserves_non_windows_command(monkeypatch) -> None:
    monkeypatch.setattr("coding_agents.adapters.process._IS_WINDOWS", False)

    assert _resolve_command(("claude", "--version")) == ("claude", "--version")


def test_resolve_command_rejects_empty_command() -> None:
    with pytest.raises(ValueError, match="进程命令不能为空"):
        _resolve_command(())


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
