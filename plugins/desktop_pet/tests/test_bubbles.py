"""A pet dismissal remains a scoped RPC and is reclaimed on teardown."""

import pytest

from agent.plugin_host.capabilities import RpcCapability
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.rpc import PluginRpcRegistry
from bus.event_bus import EventBus
from agent.plugin_host.bridge_events import PluginBridgeEvent
from plugins.desktop_pet.backend.bubbles import register_bubble_rpc


@pytest.mark.asyncio
async def test_dismiss_publishes_to_pet_background_and_unloads_cleanly():
    scope = EffectScope("desktop_pet")
    registry = PluginRpcRegistry()
    events = EventBus()
    received = []
    events.on(PluginBridgeEvent, received.append)
    register_bubble_rpc(RpcCapability(registry, scope, "desktop_pet", events))
    resolved = registry.resolve("plugin.desktop_pet.bubble.dismiss")
    assert resolved is not None
    result = await resolved[1]({})
    assert result == {"ok": True}
    assert received[0].method == "plugin.desktop_pet.bubble.dismissed"
    await scope.dispose_all()
    assert registry.resolve("plugin.desktop_pet.bubble.dismiss") is None
