from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from desktop_bridge.request_router import DesktopBridgeRequestRouter


def _router(*, role_result=None, story_result=None):
    return DesktopBridgeRequestRouter(
        roles=SimpleNamespace(handle=AsyncMock(return_value=role_result)),
        sessions_and_tasks=SimpleNamespace(handle=AsyncMock(return_value=None)),
        chat=SimpleNamespace(handle=AsyncMock(return_value=None)),
        images=SimpleNamespace(handle=AsyncMock(return_value=None)),
        voice=SimpleNamespace(handle=AsyncMock(return_value=None)),
        stories=SimpleNamespace(handle=AsyncMock(return_value=story_result)),
        observation=None,
        plugin_packages=SimpleNamespace(handle=AsyncMock(return_value=None)),
    )


@pytest.mark.asyncio
async def test_request_router_routes_health_without_a_story_handler_match() -> None:
    router = _router()

    result = await router.dispatch(
        "health",
        {},
        request_id="request-1",
        emit_event=Mock(),
    )

    assert result == {"ok": True}
    router._stories.handle.assert_awaited_once()
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


@pytest.mark.asyncio
async def test_request_router_stops_after_story_handler_matches() -> None:
    router = _router(story_result={"stories": []})

    result = await router.dispatch(
        "stories.list",
        {},
        request_id="request-3",
        emit_event=Mock(),
    )

    assert result == {"stories": []}
    router._stories.handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_router_sends_plugin_package_methods_to_their_owner() -> None:
    router = _router()
    router._plugin_packages.handle.return_value = {"plugins": []}

    result = await router.dispatch(
        "plugins.catalog",
        {},
        request_id="request-4",
        emit_event=Mock(),
    )

    assert result == {"plugins": []}
    router._plugin_packages.handle.assert_awaited_once_with("plugins.catalog", {})
    router._stories.handle.assert_not_awaited()
