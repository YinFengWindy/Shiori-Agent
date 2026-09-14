from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from agent.plugin_host.effects import EffectScope
from agent.plugin_host.events import ScopedEventBus
from bus.event_bus import EventBus


@dataclass
class _DemoEvent:
    value: str = ""


@pytest.mark.asyncio
async def test_scoped_on_is_unbound_by_dispose():
    bus = EventBus()
    scope = EffectScope("demo")
    scoped = ScopedEventBus(bus, scope)
    seen: list[str] = []

    async def handler(event: _DemoEvent) -> None:
        seen.append(event.value)

    scoped.on(_DemoEvent, handler)
    await bus.fanout(_DemoEvent(value="before"))
    assert seen == ["before"]

    await scope.dispose_all()
    await bus.fanout(_DemoEvent(value="after"))
    assert seen == ["before"]


@pytest.mark.asyncio
async def test_manual_off_then_dispose_is_safe():
    bus = EventBus()
    scope = EffectScope("demo")
    scoped = ScopedEventBus(bus, scope)

    async def handler(event: _DemoEvent) -> None:
        raise AssertionError("should not fire")

    scoped.on(_DemoEvent, handler)
    scoped.off(_DemoEvent, handler)
    await bus.fanout(_DemoEvent())
    # 插件自行 off 后，dispose 再次 off 不应报错
    assert await scope.dispose_all() == []


@pytest.mark.asyncio
async def test_non_subscription_methods_delegate_to_real_bus():
    bus = EventBus()
    scoped = ScopedEventBus(bus, EffectScope("demo"))
    seen: list[str] = []

    bus.on(_DemoEvent, lambda event: seen.append(event.value))
    # emit 等方法直接委托底层总线
    _ = await scoped.emit(_DemoEvent(value="delegated"))
    assert seen == ["delegated"]


@pytest.mark.asyncio
@pytest.mark.parametrize("subscribe_first", [True, False])
async def test_unsubscribe_precedes_resource_cleanup_in_either_registration_order(
    subscribe_first,
):
    bus = EventBus()
    scope = EffectScope("demo")
    scoped = ScopedEventBus(bus, scope)
    closing = asyncio.Event()
    release = asyncio.Event()
    seen: list[str] = []

    async def terminate():
        closing.set()
        await release.wait()

    def subscribe():
        scoped.on(_DemoEvent, lambda event: seen.append(event.value))

    if subscribe_first:
        subscribe()
    scope.add("terminate", terminate)
    if not subscribe_first:
        subscribe()
    await bus.fanout(_DemoEvent("before"))
    unloading = asyncio.create_task(scope.dispose_all())
    try:
        await asyncio.wait_for(closing.wait(), timeout=2)
        assert _DemoEvent not in bus._handlers
        await bus.fanout(_DemoEvent("during"))
    finally:
        release.set()
        assert await unloading == []
    assert seen == ["before"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["emit", "observe", "fanout", "enqueue"])
async def test_snapshot_does_not_start_scoped_handler_after_disposal(method):
    bus = EventBus()
    scope = EffectScope("demo")
    scoped = ScopedEventBus(bus, scope)
    seen: list[str] = []

    async def unload_first(event):
        await scope.dispose_all()

    bus.on(_DemoEvent, unload_first)
    scoped.on(_DemoEvent, lambda event: seen.append(event.value))
    if method == "enqueue":
        bus.enqueue(_DemoEvent("late"))
        await bus.aclose()
    else:
        await getattr(bus, method)(_DemoEvent("late"))
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("during_cleanup", [True, False])
async def test_late_subscription_is_rejected_without_registering(during_cleanup):
    bus = EventBus()
    scope = EffectScope("demo")
    scoped = ScopedEventBus(bus, scope)
    seen: list[str] = []

    def register_late():
        with pytest.raises(RuntimeError, match="已处置"):
            scoped.on(_DemoEvent, lambda event: seen.append(event.value))

    if during_cleanup:
        scope.add("register-late", register_late)
    assert await scope.dispose_all() == []
    if not during_cleanup:
        register_late()
    await bus.fanout(_DemoEvent("late"))
    assert seen == []
    assert _DemoEvent not in bus._handlers


@pytest.mark.asyncio
async def test_off_preserves_handler_identity_and_removes_duplicate_registrations():
    bus = EventBus()
    scope = EffectScope("demo")
    scoped = ScopedEventBus(bus, scope)
    seen: list[str] = []

    class Receiver:
        def handle(self, event):
            seen.append(event.value)

    receiver = Receiver()
    handler = receiver.handle
    scoped.on(_DemoEvent, handler)
    scoped.on(_DemoEvent, handler)
    # Equal bound methods with different identities must not remove each other.
    scoped.off(_DemoEvent, receiver.handle)
    await scoped.observe(_DemoEvent("before"))
    assert seen == ["before", "before"]
    scoped.off(_DemoEvent, handler)
    scoped.on(_DemoEvent, handler)
    await scoped.observe(_DemoEvent("again"))
    assert seen == ["before", "before", "again"]
    assert await scope.dispose_all() == []
    assert _DemoEvent not in bus._handlers


@pytest.mark.asyncio
async def test_scoped_emit_preserves_sync_and_async_replacements_and_exceptions():
    bus = EventBus()
    scope = EffectScope("demo")
    scoped = ScopedEventBus(bus, scope)

    async def replace(event):
        return _DemoEvent(event.value + "-async")

    def broken(event):
        raise ValueError(event.value)

    scoped.on(_DemoEvent, lambda event: _DemoEvent(event.value + "-sync"))
    scoped.on(_DemoEvent, replace)
    assert await scoped.emit(_DemoEvent("start")) == _DemoEvent("start-sync-async")
    scoped.on(_DemoEvent, broken)
    with pytest.raises(ValueError, match="start-sync-async"):
        await scoped.emit(_DemoEvent("start"))
