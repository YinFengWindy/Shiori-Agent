"""Plugin namespace routing retains peer admission and host separation."""

import pytest

from agent.plugin_host.rpc import PluginRpcRegistry
from bus.event_bus import EventBus
from desktop_bridge.method_policy import MethodPolicy
from desktop_bridge.plugin_requests import DesktopPluginRequestHandler
from shiori_sdk.rpc import Concurrency, PluginRpcError


async def test_registered_peer_rpc_runs_only_for_the_current_declared_caller():
    registry = PluginRpcRegistry[MethodPolicy](EventBus())
    registry.communication.bind_resolver(
        {"consumer": ("provider",), "provider": (), "stranger": ()}.get
    )
    saved = []

    async def append(payload):
        saved.append(payload["text"])
        return {"items": list(saved)}

    policy = MethodPolicy(concurrency=Concurrency.INTEGRATION)
    registry.register("provider.append", "provider", append, policy)
    router = DesktopPluginRequestHandler(registry)
    generation = registry.communication.generation
    context = {"plugin_id": "consumer", "generation": generation}
    assert await router.handle(
        "provider.append", {"text": "accepted", "__plugin_context": context}
    ) == {"items": ["accepted"]}
    with pytest.raises(PluginRpcError) as undeclared:
        await router.handle(
            "provider.append",
            {
                "text": "rejected",
                "__plugin_context": {**context, "plugin_id": "stranger"},
            },
        )
    assert undeclared.value.code == "plugin_dependency_undeclared"
    with pytest.raises(PluginRpcError) as stale:
        await router.handle(
            "provider.append",
            {"text": "stale", "__plugin_context": {**context, "generation": "old"}},
        )
    assert stale.value.code == "plugin_unavailable"
    assert await router.handle("plugin.provider.append", {"text": "legacy"}) is None
    assert await router.handle("roles.update", {"text": "host"}) is None
    assert saved == ["accepted"]


async def test_native_context_cannot_survive_owner_disposal():
    registry = PluginRpcRegistry[MethodPolicy](EventBus())
    registry.communication.bind_resolver({"provider": ()}.get)
    router = DesktopPluginRequestHandler(registry)
    opened = await router.handle(
        "plugins.communication.open",
        {"plugin_id": "provider", "owner": "document", "renderer": "renderer"},
    )
    assert opened is not None
    context = {"plugin_id": "provider", "owner": "document", **opened}
    assert await router.handle("plugins.communication.native.authorize", context) == {
        "plugin_id": "provider",
        **opened,
    }
    await router.handle("plugins.communication.close", context)
    with pytest.raises(PluginRpcError) as closed:
        await router.handle("plugins.communication.native.authorize", context)
    assert closed.value.code == "plugin_invalid_owner"
