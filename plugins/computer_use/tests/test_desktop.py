"""Concurrent turns cannot interleave desktop input or reuse cancelled generations."""

import asyncio

import pytest

from agent.mcp.client import McpToolError
from agent.tools.turn_scope import current_tool_turn, tool_turn
from plugins.computer_use.backend.config import ComputerUseConfig
from plugins.computer_use.backend.desktop import ComputerDesktop


class Session:
    """Controllable native boundary with observable admission and teardown."""

    def __init__(self, *_):
        self.ready = True
        self.stopped = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.close_started = asyncio.Event()
        self.close_release = asyncio.Event()
        self.close_release.set()
        self.calls = []
        self.closed = False
        self.close_error = None

    def stop(self):
        self.stopped = True

    async def call(self, name, arguments):
        if self.stopped:
            raise RuntimeError("stopped")
        self.calls.append(name)
        self.entered.set()
        if name == "wait":
            await self.release.wait()
        if name == "timeout":
            raise TimeoutError("native timeout")
        if name == "error":
            raise McpToolError(server="test", tool_name=name, message="stale")
        return name

    async def close(self):
        self.close_started.set()
        await self.close_release.wait()
        if self.close_error:
            raise self.close_error
        self.closed = True


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    sessions = []

    def factory(*args):
        session = Session(*args)
        sessions.append(session)
        return session

    monkeypatch.setattr("plugins.computer_use.backend.desktop.DesktopSession", factory)
    return ComputerDesktop(tmp_path, ComputerUseConfig()), sessions


async def test_ownership_persists_between_calls_and_roles(desktop):
    manager, sessions = desktop
    observed, resume = asyncio.Event(), asyncio.Event()

    @tool_turn
    async def owner():
        assert await manager.call("role-a", "observe", {}) == "observe"
        observed.set()
        await resume.wait()  # The model is thinking; desktop must stay leased.
        await manager.call("role-a", "input", {})

    @tool_turn
    async def contender(role):
        with pytest.raises(RuntimeError, match="占用"):
            await manager.call(role, "input", {})

    task = asyncio.create_task(owner())
    await observed.wait()
    await asyncio.gather(contender("role-b"), contender("role-a"))
    assert sessions[0].calls == ["observe"]
    resume.set()
    await task
    assert sessions[0].closed

    @tool_turn
    async def next_turn():
        await manager.call("role-b", "input", {})

    await next_turn()
    assert len(sessions) == 2 and sessions[1].closed


async def test_timeout_revokes_whole_turn_but_completed_error_can_reobserve(desktop):
    manager, sessions = desktop

    @tool_turn
    async def turn():
        with pytest.raises(McpToolError):
            await manager.call("role", "error", {})
        await manager.call("role", "observe", {})
        with pytest.raises(TimeoutError):
            await manager.call("role", "timeout", {})
        with pytest.raises(RuntimeError, match="已停止"):
            await manager.call("role", "input", {})

    await turn()
    assert sessions[0].calls == ["error", "observe", "timeout"]
    assert sessions[0].closed


async def test_unload_stops_pending_calls_and_keeps_cleanup_after_double_cancel(
    desktop,
):
    manager, sessions = desktop
    scopes = []

    @tool_turn
    async def turn():
        scopes.append(current_tool_turn())
        await manager.call("role", "wait", {})

    owner = asyncio.create_task(turn())
    while not sessions:
        await asyncio.sleep(0)
    session = sessions[0]
    await session.entered.wait()
    session.close_release.clear()
    closing = asyncio.create_task(manager.close())
    await session.close_started.wait()
    closing.cancel()
    owner.cancel()
    while not scopes[0].closed:
        await asyncio.sleep(0)
    owner.cancel()
    await asyncio.gather(owner, closing, return_exceptions=True)
    assert session.stopped and not session.closed
    with pytest.raises(RuntimeError, match="已停用"):
        await manager.call("role", "input", {})
    session.close_release.set()
    await manager.close()
    assert session.closed
    assert session.calls == ["wait"]


async def test_abandoned_cleanup_failure_remains_visible_to_unload(desktop):
    manager, sessions = desktop
    entered, release = asyncio.Event(), asyncio.Event()

    @tool_turn
    async def turn():
        await manager.call("role", "observe", {})
        sessions[0].close_release.clear()
        sessions[0].close_error = RuntimeError("cleanup failed")
        entered.set()
        await release.wait()

    task = asyncio.create_task(turn())
    await entered.wait()
    task.cancel()
    await sessions[0].close_started.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    sessions[0].close_release.set()
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await manager.close()
    assert not sessions[0].closed


async def test_explicit_release_and_late_descendant_cannot_restart(desktop):
    manager, sessions = desktop
    continue_late = asyncio.Event()

    async def late():
        await continue_late.wait()
        with pytest.raises(RuntimeError, match="有效的宿主"):
            await manager.call("role", "input", {})

    @tool_turn
    async def turn():
        await manager.call("role", "observe", {})
        child = asyncio.create_task(late())
        await manager.call("role", "release", {})
        with pytest.raises(RuntimeError, match="已停止"):
            await manager.call("role", "input", {})
        return child

    child = await turn()
    continue_late.set()
    await child
    assert sessions[0].closed and sessions[0].calls == ["observe"]
