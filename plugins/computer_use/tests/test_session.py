"""Injected Driver startup and stop behavior."""

from shiori_sdk.testing.processes import FakeProcesses, current_tool_turn

import asyncio

import pytest

from shiori_sdk.testing.processes import tool_turn
from plugins.computer_use.backend.config import ComputerUseConfig
from plugins.computer_use.backend.desktop import ComputerDesktop


@pytest.fixture
def native_boundary(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from plugins.computer_use.backend.session import DesktopSession

    lease = SimpleNamespace(closed=False)

    def close_lease():
        lease.closed = True

    lease.close = close_lease
    client = SimpleNamespace(
        connect=AsyncMock(), call=AsyncMock(return_value="done"), disconnect=AsyncMock()
    )
    monkeypatch.setattr(
        "plugins.computer_use.backend.session.resolve_driver",
        lambda _: tmp_path / "driver.exe",
    )
    monkeypatch.setattr(
        "plugins.computer_use.backend.session.DesktopLease", lambda: lease
    )
    monkeypatch.setattr(
        "plugins.computer_use.backend.session.driver_client", lambda *_: client
    )
    session = DesktopSession(
        tmp_path, ComputerUseConfig(), processes=FakeProcesses(), resources=tmp_path
    )
    session._targets = Mock(validate=Mock(return_value=None))
    return session, client, lease


async def test_stop_prevents_queued_input_and_retains_lease_until_disconnect(
    native_boundary,
):
    session, client, lease = native_boundary
    entered, disconnecting, finish = (asyncio.Event() for _ in range(3))

    async def blocked(*_args, **_kwargs):
        entered.set()
        await asyncio.Future()

    async def disconnect():
        disconnecting.set()
        await finish.wait()

    client.call.side_effect = blocked
    client.disconnect.side_effect = disconnect
    active = asyncio.create_task(session.call("click", {}))
    await entered.wait()
    queued = asyncio.create_task(session.call("type_text", {}))
    await asyncio.sleep(0)
    assert client.call.await_count == 1
    session.stop()
    active.cancel()
    results = await asyncio.gather(active, queued, return_exceptions=True)
    assert isinstance(results[0], asyncio.CancelledError)
    assert isinstance(results[1], RuntimeError)
    closing = asyncio.create_task(session.close())
    await disconnecting.wait()
    assert not lease.closed
    finish.set()
    await closing
    assert lease.closed and client.call.await_count == 1


async def test_startup_protocol_failure_releases_native_resources(
    native_boundary, tmp_path
):
    from shiori_sdk.mcp import McpToolError

    _session, client, lease = native_boundary
    client.connect.side_effect = McpToolError(
        server="test", tool_name="initialize", message="startup failed"
    )
    manager = ComputerDesktop(
        tmp_path,
        ComputerUseConfig(),
        processes=FakeProcesses(),
        resources=tmp_path,
        current_turn=current_tool_turn,
    )

    @tool_turn
    async def run():
        with pytest.raises(McpToolError, match="startup failed"):
            await manager.call("role", "list_windows", {})
        with pytest.raises(RuntimeError, match="已停止"):
            await manager.call("role", "click", {})

    await run()
    assert lease.closed
    client.disconnect.assert_awaited_once()
    client.call.assert_not_awaited()
