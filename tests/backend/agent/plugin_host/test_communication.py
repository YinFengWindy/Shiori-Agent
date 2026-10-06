"""Namespace admission and renderer rendezvous lifetime regression coverage."""

import asyncio

import pytest

from agent.plugin_host.bridge_events import PluginBridgeEvent
from shiori_sdk.rpc import PluginRpcError
from agent.plugin_host.communication import communication_name
from agent.plugin_host.rpc import PluginRpcRegistry
from bus.event_bus import EventBus


def communication():
    registry = PluginRpcRegistry()
    bus = EventBus()
    active = {"consumer": ("provider", "missing"), "provider": ()}
    registry.communication.configure(active.get, bus)
    return registry.communication, bus, active


async def context(comm, plugin="consumer", owner="ui"):
    opened = await comm.handle("open", {"plugin_id": plugin, "owner": owner})
    return {"plugin_id": plugin, "owner": owner, **opened}


@pytest.mark.asyncio
async def test_declarations_resolve_missing_and_disabled_without_enabling():
    comm, _, active = communication()
    caller = await context(comm)
    assert await comm.handle("resolve", {**caller, "target": "provider"}) == {
        "available": True
    }
    assert await comm.handle("resolve", {**caller, "target": "missing"}) == {
        "available": False
    }
    with pytest.raises(PluginRpcError, match="未声明"):
        await comm.handle("resolve", {**caller, "target": "unknown"})
    del active["provider"]
    assert await comm.handle("resolve", {**caller, "target": "provider"}) == {
        "available": False
    }
    assert "provider" not in active


@pytest.mark.asyncio
@pytest.mark.parametrize("retire", ["provider", "consumer", "generation"])
async def test_removing_either_plugin_or_generation_rejects_pending(retire):
    comm, bus, _ = communication()
    caller = await context(comm)
    provider = await context(comm, "provider", "background")
    await comm.handle("register", {**provider, "name": "sync"})
    received = asyncio.Event()

    def dispatch(event):
        event.dispatched = True
        received.set()

    bus.on(PluginBridgeEvent, dispatch)
    task = asyncio.create_task(
        comm.handle("call", {**caller, "target": "provider", "name": "sync"})
    )
    await received.wait()
    if retire == "generation":
        comm.retire()
    else:
        comm.remove_plugin(retire)
    with pytest.raises(PluginRpcError, match="停用或替换"):
        await task
    assert not comm._requests.pending
    if retire != "consumer":
        assert not comm._handlers


@pytest.mark.asyncio
async def test_background_replies_preserve_errors_and_validate_provider_identity():
    comm, bus, _ = communication()
    caller = await context(comm)
    provider = await context(comm, "provider", "background")
    await comm.handle("register", {**provider, "name": "sync"})

    async def dispatch(event):
        event.dispatched = True
        with pytest.raises(PluginRpcError, match="来源不匹配"):
            await comm.handle(
                "reply", {**caller, "request_id": event.payload["request_id"]}
            )
        await comm.handle(
            "reply",
            {
                **provider,
                "request_id": event.payload["request_id"],
                "error": {"code": "binding_failed", "message": "binding missing"},
            },
        )

    bus.on(PluginBridgeEvent, dispatch)
    with pytest.raises(PluginRpcError, match="binding missing") as failure:
        await comm.handle("call", {**caller, "target": "provider", "name": "sync"})
    assert failure.value.code == "binding_failed"
    assert not comm._requests.pending


@pytest.mark.asyncio
async def test_closed_owner_does_not_remove_replacement_registration():
    comm, _, _ = communication()
    old = await context(comm, "provider", "old")
    await comm.handle("register", {**old, "name": "sync"})
    await comm.handle("close", old)
    new = await context(comm, "provider", "new")
    await comm.handle("register", {**new, "name": "sync"})
    await comm.handle("close", old)
    assert comm._handlers == {("provider", "sync"): "new"}
    comm.retire()
    with pytest.raises(PluginRpcError, match="代际"):
        await comm.handle("register", {**new, "name": "again"})


@pytest.mark.asyncio
async def test_renderer_disconnect_reclaims_only_its_registered_contexts():
    comm, _, _ = communication()
    first = {"plugin_id": "provider", "owner": "background", "renderer": "window-1"}
    first.update(await comm.handle("open", first))
    await comm.handle("register", {**first, "name": "sync"})
    other = {"plugin_id": "consumer", "owner": "ui", "renderer": "window-2"}
    other.update(await comm.handle("open", other))
    await comm.handle("disconnect", {"renderer": "window-1"})
    assert not comm._handlers
    assert comm._owners == {"ui": "consumer"}
    assert await comm.handle("resolve", {**other, "target": "provider"}) == {
        "available": True
    }


@pytest.mark.asyncio
async def test_delayed_departed_document_disconnect_preserves_successor_routing():
    comm, bus, _ = communication()
    caller = await context(comm)
    old = {"plugin_id": "provider", "owner": "old", "renderer": "document-1"}
    old.update(await comm.handle("open", old))
    await comm.handle("register", {**old, "name": "sync"})
    await comm.handle("disconnect", {"renderer": "document-1"})
    new = {"plugin_id": "provider", "owner": "new", "renderer": "document-2"}
    new.update(await comm.handle("open", new))
    await comm.handle("register", {**new, "name": "sync"})
    await comm.handle("disconnect", {"renderer": "document-1"})

    async def reply(event):
        event.dispatched = True
        assert event.payload["owner"] == "new"
        await comm.handle(
            "reply",
            {**new, "request_id": event.payload["request_id"], "result": {"ok": True}},
        )

    bus.on(PluginBridgeEvent, reply)
    assert await comm.handle(
        "call", {**caller, "target": "provider", "name": "sync"}
    ) == {"result": {"ok": True}}


@pytest.mark.parametrize("name", ["plugin.provider.sync", "", "../sync", "sync..now"])
def test_local_names_cannot_escape_the_injected_namespace(name):
    with pytest.raises(PluginRpcError):
        communication_name(name)


@pytest.mark.asyncio
async def test_dynamic_services_require_current_owner_and_do_not_require_static_peers():
    from agent.plugin_host.effects import EffectScope

    registry = PluginRpcRegistry()
    active = {"consumer": (), "neutral_provider": ()}
    comm = registry.communication
    comm.configure(active.get, EventBus())
    caller = await context(comm)
    scope = EffectScope("neutral_provider")

    async def recognize(payload):
        return {"text": payload["audio_base64"]}

    registry.services.register(
        "neutral_provider",
        "recognizer",
        contract="shiori.asr.v1",
        label="Neutral",
        methods={"transcribe": recognize},
        metadata={},
        scope=scope,
    )
    listing = await comm.handle(
        "services.list", {**caller, "contract": "shiori.asr.v1"}
    )
    assert listing["services"][0]["plugin_id"] == "neutral_provider"
    request = {
        **caller,
        "service": {"plugin_id": "neutral_provider", "service_id": "recognizer"},
        "name": "transcribe",
        "payload": {"audio_base64": "recording"},
    }
    assert await comm.handle("services.call", request) == {"text": "recording"}
    assert await comm.handle("native.authorize", caller) == {
        "plugin_id": "consumer",
        "generation": comm.generation,
    }
    for operation in ("services.call", "native.authorize"):
        with pytest.raises(PluginRpcError, match="上下文"):
            await comm.handle(operation, {**request, "plugin_id": "neutral_provider"})
    await scope.dispose_all()
    with pytest.raises(PluginRpcError, match="不可用"):
        await comm.handle("services.call", request)
    await comm.handle("close", caller)
    with pytest.raises(PluginRpcError, match="上下文"):
        await comm.handle("services.list", {**caller, "contract": "shiori.asr.v1"})


@pytest.mark.asyncio
@pytest.mark.parametrize("retire", ["context", "generation"])
async def test_service_call_finishes_provider_work_but_rejects_retired_caller_result(
    retire,
):
    from agent.plugin_host.effects import EffectScope

    registry = PluginRpcRegistry()
    comm = registry.communication
    comm.configure({"consumer": (), "provider": ()}.get, EventBus())
    caller = await context(comm)
    started, finish = asyncio.Event(), asyncio.Event()
    completed = []

    async def slow(_payload):
        started.set()
        await finish.wait()
        completed.append(True)
        return {"result": "late"}

    registry.services.register(
        "provider",
        "slow",
        contract="neutral.v1",
        label="Slow",
        methods={"run": slow},
        metadata={},
        scope=EffectScope("provider"),
    )
    pending = asyncio.create_task(
        comm.handle(
            "services.call",
            {
                **caller,
                "service": {"plugin_id": "provider", "service_id": "slow"},
                "name": "run",
                "payload": {},
            },
        )
    )
    await started.wait()
    if retire == "generation":
        comm.retire()
    else:
        await comm.handle("close", caller)
    assert not pending.done()
    finish.set()
    with pytest.raises(PluginRpcError, match="停用"):
        await pending
    assert completed == [True]
