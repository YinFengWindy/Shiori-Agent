"""Requests across the real plugin UI host boundary."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from shiori_sdk.bridge import BridgeResponse


class PluginBridgeService(Protocol):
    """The portion of the desktop service needed by bridge integration tests."""

    async def handle(
        self,
        request: dict[str, Any],
        *,
        emit_event: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> BridgeResponse: ...


def _discard_event(_event: dict[str, Any]) -> None:
    """Drops bridge events when a test only needs the request response."""


async def plugin_bridge_request(
    service: PluginBridgeService,
    method: str,
    payload: dict[str, Any] | None = None,
) -> BridgeResponse:
    """Sends a request through the same host boundary used by plugin UI."""
    return await service.handle(
        {"id": method, "method": method, "payload": payload or {}},
        emit_event=_discard_event,
    )
