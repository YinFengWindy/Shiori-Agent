"""Plugin registrations cannot claim a host or another plugin's namespace."""

import pytest

from agent.plugin_host.rpc import PluginRpcRegistry
from bus.event_bus import EventBus
from desktop_bridge.method_policy import MethodPolicy
from shiori_sdk.rpc import Concurrency


async def test_namespace_rejection_cannot_replace_a_host_or_peer_method():
    registry = PluginRpcRegistry[MethodPolicy](EventBus())

    async def original(payload):
        return {"saved": True}

    custom = MethodPolicy(concurrency=Concurrency.INTEGRATION)
    registry.register("provider.save", "provider", original, custom)
    with pytest.raises(ValueError):
        registry.register("provider.save", "stranger", original, MethodPolicy())
    with pytest.raises(ValueError):
        registry.register("roles.list", "roles", original, custom)
    resolved = registry.resolve("provider.save")
    assert resolved is not None
    assert await resolved[1]({}) == {"saved": True}
    assert registry.resolve("roles.list") is None
