from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from desktop_bridge.request_router import DesktopBridgeRequestRouter


def _router(*, role_result=None, world_result=None):
    return DesktopBridgeRequestRouter(
        roles=SimpleNamespace(handle=AsyncMock(return_value=role_result)),
        sessions_and_tasks=SimpleNamespace(handle=AsyncMock(return_value=None)),
        chat=SimpleNamespace(handle=AsyncMock(return_value=None)),
        images=SimpleNamespace(handle=AsyncMock(return_value=None)),
        voice=SimpleNamespace(handle=AsyncMock(return_value=None)),
        worlds=SimpleNamespace(handle=Mock(return_value=world_result)),
        observation=None,
    )


@pytest.mark.asyncio
async def test_request_router_preserves_world_before_health_routing() -> None:
    router = _router()

    result = await router.dispatch(
        "health",
        {},
        request_id="request-1",
        emit_event=Mock(),
    )

    assert result == {"ok": True}
    router._worlds.handle.assert_called_once_with(
        "health",
        {},
        request_id="request-1",
    )
    router._voice.handle.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_router_stops_after_the_owning_handler_matches() -> None:
    router = _router(role_result={"roles": []})

    result = await router.dispatch(
        "roles.list",
        {},
        request_id="request-2",
        emit_event=Mock(),
    )

    assert result == {"roles": []}
    router._roles.handle.assert_awaited_once_with("roles.list", {})
    router._sessions_and_tasks.handle.assert_not_awaited()
    router._chat.handle.assert_not_awaited()
    router._images.handle.assert_not_awaited()
