"""Injected MCP and daemon resource failure boundaries."""

from shiori_sdk.testing.processes import FakeProcesses

from unittest.mock import AsyncMock, Mock

import pytest

from plugins.browser_use.backend.config import BrowserUseConfig
from plugins.browser_use.backend.runtime import BrowserRuntime
from plugins.browser_use.backend.session import BrowserSession


async def test_cleanup_releases_profile_even_when_job_fails(tmp_path):
    session = BrowserSession(
        tmp_path,
        "role",
        BrowserUseConfig(),
        BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
        processes=FakeProcesses(),
    )
    session._client = AsyncMock()
    session._daemon = AsyncMock()
    session._daemon.close.side_effect = RuntimeError("job failure")
    lease = Mock()
    session._lease = lease
    with pytest.raises(RuntimeError, match="job failure"):
        await session.close()
    lease.close.assert_called_once()


@pytest.mark.parametrize("phase", ["initialize", "tools/list"])
async def test_mcp_startup_errors_release_profile_and_native_resources(
    tmp_path, monkeypatch, phase
):
    from shiori_sdk.testing.processes import FakeMcpSession
    from shiori_sdk.mcp import McpToolError
    from plugins.browser_use.backend.daemon import BrowserDaemon
    from plugins.browser_use.backend.profile import ProfileLease

    daemon_close = AsyncMock()
    disconnect = AsyncMock()
    operation = AsyncMock()
    error = McpToolError(
        server="browser_use", tool_name=phase, message="controlled init failure"
    )
    monkeypatch.setattr(BrowserDaemon, "start", AsyncMock())
    monkeypatch.setattr(BrowserDaemon, "close", daemon_close)
    monkeypatch.setattr(FakeMcpSession, "connect", AsyncMock(side_effect=error))
    monkeypatch.setattr(FakeMcpSession, "disconnect", disconnect)
    monkeypatch.setattr(FakeMcpSession, "call", operation)
    session = BrowserSession(
        tmp_path,
        "role",
        BrowserUseConfig(),
        BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
        processes=FakeProcesses(),
    )
    with pytest.raises(McpToolError) as raised:
        await session.call("agent_browser_open", {})
    assert raised.value is error
    assert session.closed and session._lease is None
    assert session._client is session._daemon is None
    daemon_close.assert_awaited_once()
    disconnect.assert_awaited_once()
    operation.assert_not_awaited()
    lease = ProfileLease(session.profile)
    lease.close()


async def test_completed_tool_error_keeps_established_page_and_profile(
    tmp_path, monkeypatch
):
    from shiori_sdk.testing.processes import FakeMcpSession
    from shiori_sdk.mcp import McpToolError
    from plugins.browser_use.backend.daemon import BrowserDaemon

    daemon_close = AsyncMock()
    disconnect = AsyncMock()
    error = McpToolError(
        server="browser_use", tool_name="agent_browser_click", message="stale ref"
    )
    remote = AsyncMock(side_effect=["opened", error, "fresh snapshot", "closed"])
    monkeypatch.setattr(BrowserDaemon, "start", AsyncMock())
    monkeypatch.setattr(BrowserDaemon, "close", daemon_close)
    monkeypatch.setattr(FakeMcpSession, "connect", AsyncMock())
    monkeypatch.setattr(FakeMcpSession, "disconnect", disconnect)
    monkeypatch.setattr(FakeMcpSession, "call", remote)
    session = BrowserSession(
        tmp_path,
        "role",
        BrowserUseConfig(),
        BrowserRuntime(tmp_path / "binary", tmp_path / "chrome"),
        processes=FakeProcesses(),
    )
    await session.call("agent_browser_open", {})
    client = session._client
    with pytest.raises(McpToolError, match="stale ref"):
        await session.call("agent_browser_click", {"selector": "@old"})
    assert not session.closed and session._lease is not None
    assert session._client is client
    daemon_close.assert_not_awaited()
    disconnect.assert_not_awaited()
    assert await session.call("agent_browser_snapshot", {}) == "fresh snapshot"
    await session.close(graceful=True)
