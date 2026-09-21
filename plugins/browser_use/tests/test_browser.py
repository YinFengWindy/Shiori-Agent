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
    assert not manager._sessions
