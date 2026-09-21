"""Session manager cancellation preserves ownership, including calls queued on a lock."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from plugins.browser_use.backend.browser import BrowserSessions
from plugins.browser_use.backend.config import BrowserUseConfig
from plugins.browser_use.backend.runtime import BrowserRuntime
from plugins.browser_use.backend.session import BrowserSession


@pytest.fixture
def manager(tmp_path, monkeypatch):
    async def start(session):
        session._client = AsyncMock()
        session._client.call.return_value = "ok"

    monkeypatch.setattr(BrowserSession, "_start", start)
    return BrowserSessions(
        tmp_path,
        BrowserUseConfig(),
        runtime=BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )


async def test_cancelled_queued_call_keeps_active_session_owned(manager):
    assert await manager.call("role", "open", {}) == "ok"
    session = manager._sessions["role"]
    started = asyncio.Event()
    finish = asyncio.Event()

    async def action(*_, **__):
        started.set()
        await finish.wait()
        return "finished"

    session._client.call.side_effect = action
    active = asyncio.create_task(manager.call("role", "click", {}))
    await started.wait()
    queued = asyncio.create_task(manager.call("role", "fill", {}))
    await asyncio.sleep(0.01)
    queued.cancel()
    with pytest.raises(asyncio.CancelledError):
        await queued
    assert manager._sessions["role"] is session
    assert not session.closed
    finish.set()
    assert await active == "finished"
    await manager.close()
    assert session.closed


async def test_failed_start_can_be_retried_with_a_new_generation(manager, monkeypatch):
    original = BrowserSession._start
    monkeypatch.setattr(
        BrowserSession, "_start", AsyncMock(side_effect=RuntimeError("missing runtime"))
    )
    with pytest.raises(RuntimeError, match="missing runtime"):
        await manager.call("role", "open", {})
    assert not manager._sessions
    monkeypatch.setattr(BrowserSession, "_start", original)
    assert await manager.call("role", "open", {}) == "ok"
    await manager.close()


async def test_unload_cancels_current_and_queued_calls(manager):
    await manager.call("role", "open", {})
    session = manager._sessions["role"]
    started = asyncio.Event()

    async def action(*_, **__):
        started.set()
        await asyncio.Event().wait()

    session._client.call.side_effect = action
    first = asyncio.create_task(manager.call("role", "click", {}))
    await started.wait()
    second = asyncio.create_task(manager.call("role", "fill", {}))
    await asyncio.sleep(0.01)
    await manager.close()
    assert session.closed
    for task in (first, second):
        with pytest.raises(asyncio.CancelledError):
            await task
    with pytest.raises(RuntimeError, match="已停用"):
        await manager.call("role", "open", {})


async def test_close_reaps_all_roles_even_if_one_fails(manager):
    await manager.call("first", "open", {})
    await manager.call("second", "open", {})
    first, second = manager._sessions.values()
    first._client.call.side_effect = RuntimeError("close failure")
    with pytest.raises(ExceptionGroup, match="清理失败"):
        await manager.close()
    assert first.closed and second.closed
    assert manager._sessions == {"first": first}
    # Failed cleanup retains its owner for a later unload/close retry.
    await manager.close()
    assert not manager._sessions


@pytest.mark.parametrize("phase", ["daemon", "mcp"])
async def test_close_during_startup_cancels_old_actions_before_releasing_owner(
    tmp_path, monkeypatch, phase
):
    from agent.mcp.client import McpClient
    from plugins.browser_use.backend.daemon import BrowserDaemon
    from plugins.browser_use.backend.profile import ProfileLease

    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    allow_cleanup = asyncio.Event()

    async def blocked_start(*_, **__):
        started.set()
        await asyncio.Event().wait()

    async def blocked_cleanup(*_, **__):
        cleanup_started.set()
        await allow_cleanup.wait()

    daemon_start = AsyncMock(side_effect=blocked_start if phase == "daemon" else None)
    connect = AsyncMock(side_effect=blocked_start if phase == "mcp" else None)
    daemon_close = AsyncMock(side_effect=blocked_cleanup)
    disconnect = AsyncMock()
    action = AsyncMock(return_value="action AFTER close")
    monkeypatch.setattr(BrowserDaemon, "start", daemon_start)
    monkeypatch.setattr(BrowserDaemon, "close", daemon_close)
    monkeypatch.setattr(McpClient, "connect", connect)
    monkeypatch.setattr(McpClient, "disconnect", disconnect)
    monkeypatch.setattr(McpClient, "call", action)
    manager = BrowserSessions(
        tmp_path,
        BrowserUseConfig(),
        runtime=BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )
    opening = asyncio.create_task(manager.call("role", "agent_browser_open", {}))
    await started.wait()
    session = manager._sessions["role"]
    queued_admitted = asyncio.Event()

    async def queued_action():
        queued_admitted.set()
        return await manager.call("role", "agent_browser_fill", {})

    queued = asyncio.create_task(queued_action())
    await queued_admitted.wait()
    closing = asyncio.create_task(manager.call("role", "agent_browser_close", {}))
    await cleanup_started.wait()
    assert not closing.done()
    assert manager._sessions["role"] is session
    assert session._lease is not None
    with pytest.raises(RuntimeError, match="正在关闭"):
        await manager.call("role", "agent_browser_open", {})
    with pytest.raises(RuntimeError, match="占用"):
        ProfileLease(session.profile)
    allow_cleanup.set()
    result = await closing
    assert isinstance(result, str) and "已关闭" in result
    for task in (opening, queued):
        with pytest.raises(asyncio.CancelledError):
            await task
    assert session.closed and session._lease is None
    assert session._client is session._daemon is None
    assert not manager._sessions
    action.assert_not_awaited()
    daemon_close.assert_awaited_once()
    assert disconnect.await_count == (1 if phase == "mcp" else 0)
    lease = ProfileLease(session.profile)
    lease.close()
    await manager.close()


async def test_mcp_initialization_error_retires_generation_before_retry(
    tmp_path, monkeypatch
):
    from agent.mcp.client import McpClient, McpToolError
    from plugins.browser_use.backend.daemon import BrowserDaemon

    error = McpToolError(
        server="browser_use", tool_name="initialize", message="controlled init failure"
    )
    monkeypatch.setattr(BrowserDaemon, "start", AsyncMock())
    daemon_close = AsyncMock()
    disconnect = AsyncMock()
    monkeypatch.setattr(BrowserDaemon, "close", daemon_close)
    monkeypatch.setattr(McpClient, "connect", AsyncMock(side_effect=[error, []]))
    monkeypatch.setattr(
        McpClient, "call", AsyncMock(return_value="new generation opened")
    )
    monkeypatch.setattr(McpClient, "disconnect", disconnect)
    manager = BrowserSessions(
        tmp_path,
        BrowserUseConfig(),
        runtime=BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )
    with pytest.raises(McpToolError) as raised:
        await manager.call("role", "agent_browser_open", {})
    assert raised.value is error
    assert not manager._sessions and not manager._closing
    daemon_close.assert_awaited_once()
    disconnect.assert_awaited_once()
    assert (
        await manager.call("role", "agent_browser_open", {}) == "new generation opened"
    )
    await manager.close()


async def test_cancelled_close_is_owned_until_plugin_unload_finishes(
    tmp_path, monkeypatch
):
    from agent.mcp.client import McpClient
    from plugins.browser_use.backend.daemon import BrowserDaemon

    close_started = asyncio.Event()
    allow_close = asyncio.Event()
    unload_started = asyncio.Event()

    async def remote_call(name, *_, **__):
        if name == "agent_browser_close":
            close_started.set()
            await allow_close.wait()
        return "ok"

    monkeypatch.setattr(BrowserDaemon, "start", AsyncMock())
    daemon_close = AsyncMock()
    disconnect = AsyncMock()
    monkeypatch.setattr(BrowserDaemon, "close", daemon_close)
    monkeypatch.setattr(McpClient, "connect", AsyncMock())
    monkeypatch.setattr(McpClient, "call", AsyncMock(side_effect=remote_call))
    monkeypatch.setattr(McpClient, "disconnect", disconnect)
    manager = BrowserSessions(
        tmp_path,
        BrowserUseConfig(),
        runtime=BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )
    await manager.call("role", "agent_browser_open", {})
    session = manager._sessions["role"]
    closing = asyncio.create_task(manager.call("role", "agent_browser_close", {}))
    await close_started.wait()
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert manager._sessions["role"] is session
    assert not manager._closing["role"].done()

    async def unload():
        unload_started.set()
        await manager.close()

    unloading = asyncio.create_task(unload())
    await unload_started.wait()
    assert not unloading.done()
    assert session._lease is not None
    allow_close.set()
    await unloading
    assert not manager._sessions and not manager._closing
    assert session._lease is None
    daemon_close.assert_awaited_once()
    disconnect.assert_awaited_once()


async def test_abandoned_close_failure_remains_owned_until_unload_observes_it(manager):
    await manager.call("role", "agent_browser_open", {})
    session = manager._sessions["role"]
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    failure = RuntimeError("controlled close failure")

    async def failed_close(*_, **__):
        started.set()
        await release.wait()
        raise failure

    session._client.call.side_effect = failed_close
    closing = asyncio.create_task(manager.call("role", "agent_browser_close", {}))
    await started.wait()
    owned = manager._closing["role"]
    owned.add_done_callback(lambda _: finished.set())
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    release.set()
    await finished.wait()
    # Do not inspect owned.exception(): unload must be the first observer.
    assert manager._closing["role"] is owned
    assert manager._sessions["role"] is session
    with pytest.raises(ExceptionGroup) as raised:
        await manager.close()
    assert raised.value.exceptions == (failure,)
    assert not manager._closing
    # The observed failure is reported once; cleanup can then be retried.
    await manager.close()
    assert not manager._sessions


async def test_closing_one_role_does_not_serialize_other_roles(tmp_path, monkeypatch):
    from agent.mcp.client import McpClient
    from plugins.browser_use.backend.daemon import BrowserDaemon

    blocked = asyncio.Event()
    cleanup = asyncio.Event()
    release = asyncio.Event()

    async def start(daemon, _):
        if not blocked.is_set():
            blocked.set()
            await asyncio.Event().wait()

    async def close(daemon):
        cleanup.set()
        await release.wait()

    monkeypatch.setattr(BrowserDaemon, "start", start)
    monkeypatch.setattr(BrowserDaemon, "close", close)
    monkeypatch.setattr(McpClient, "connect", AsyncMock())
    monkeypatch.setattr(
        McpClient, "call", AsyncMock(return_value="other role succeeds")
    )
    monkeypatch.setattr(McpClient, "disconnect", AsyncMock())
    manager = BrowserSessions(
        tmp_path,
        BrowserUseConfig(),
        runtime=BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
    )
    first = asyncio.create_task(manager.call("first", "agent_browser_open", {}))
    await blocked.wait()
    closing = asyncio.create_task(manager.call("first", "agent_browser_close", {}))
    await cleanup.wait()
    assert (
        await asyncio.wait_for(manager.call("second", "agent_browser_open", {}), 1)
        == "other role succeeds"
    )
    release.set()
    await closing
    with pytest.raises(asyncio.CancelledError):
        await first
    assert "second" in manager._sessions and "first" not in manager._sessions
    await manager.close()
