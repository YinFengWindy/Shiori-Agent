"""Kernel lifecycle: failure propagation, reload closure, draining and providers."""

import asyncio
import itertools
from dataclasses import dataclass

import pytest

from shiori_sdk.kernel import (
    Context,
    Kernel,
    KernelError,
    Key,
    PluginFailed,
    PluginSpec,
    PluginStarted,
    PluginStopped,
)
from shiori_sdk.testing.kernel import KernelHarness

SERVICE = Key[object]("service")


@dataclass(frozen=True)
class Ping:
    trail: tuple[str, ...] = ()


@dataclass(frozen=True)
class Generation:
    number: int


async def _idle(ctx: Context) -> None:
    return None


async def test_setup_failure_blocks_requirers_and_optional_consumers_get_none() -> None:
    seen: dict[str, object] = {}

    async def broken(ctx: Context) -> None:
        ctx.provide(SERVICE, object())
        raise RuntimeError("cannot start")

    async def hard(ctx: Context) -> None:
        seen["hard"] = "ran"

    async def soft(ctx: Context) -> None:
        seen["soft"] = ctx.get(SERVICE)

    kernel = Kernel()
    await kernel.start(
        [
            PluginSpec("provider", broken, provides=("service",)),
            PluginSpec("hard", hard, requires=("service",)),
            PluginSpec("soft", soft, optional=("service",)),
        ]
    )

    failed = kernel.status("provider")
    blocked = kernel.status("hard")
    assert failed is not None and failed.state == "FAILED"
    assert failed.diagnostic is not None and "cannot start" in failed.diagnostic.reason
    assert blocked is not None and blocked.state == "BLOCKED"
    assert blocked.diagnostic is not None and "service" in blocked.diagnostic.reason
    assert seen == {"soft": None}
    assert kernel.get(SERVICE) is None


async def test_lifecycle_events_report_started_failed_and_stopped() -> None:
    seen: list[object] = []

    async def observe(ctx: Context) -> None:
        async def record(event: object) -> None:
            seen.append(event)

        for event_type in (PluginStarted, PluginFailed, PluginStopped):
            ctx.watch(event_type, record)

    async def broken(ctx: Context) -> None:
        raise RuntimeError("boom")

    harness = KernelHarness()
    kernel = await harness.start(
        PluginSpec("observe", observe),
        PluginSpec("worker", _idle),
        PluginSpec("zz_broken", broken),
    )
    _ = await kernel.deactivate("worker")
    await harness.idle()

    assert [(type(event).__name__, getattr(event, "plugin_id")) for event in seen] == [
        ("PluginStarted", "observe"),
        ("PluginStarted", "worker"),
        ("PluginFailed", "zz_broken"),
        ("PluginStopped", "worker"),
    ]
    failed = seen[2]
    assert isinstance(failed, PluginFailed)
    assert failed.diagnostic.state == "FAILED"


async def test_require_and_provide_must_be_declared_in_the_manifest() -> None:
    async def sneaky(ctx: Context) -> None:
        ctx.require(SERVICE)

    async def overreach(ctx: Context) -> None:
        ctx.provide(SERVICE, object())

    kernel = Kernel()
    kernel.provide(SERVICE, object())
    await kernel.start([PluginSpec("sneaky", sneaky), PluginSpec("over", overreach)])

    for plugin_id in ("sneaky", "over"):
        status = kernel.status(plugin_id)
        assert status is not None and status.state == "FAILED"
        assert isinstance(status.error, KernelError)
        assert status.error.diagnostic.code == "undeclared_key"


def _chain_member(
    name: str, requires: tuple[str, ...] = (), provides: tuple[str, ...] = ()
) -> PluginSpec:
    async def setup(ctx: Context) -> None:
        async def mark(event: Ping) -> Ping:
            return Ping((*event.trail, name))

        ctx.on(Ping, mark)
        for key in provides:
            ctx.provide(Key[object](key), object())

    return PluginSpec(name, setup, requires=requires, provides=provides)


async def test_reload_keeps_the_cold_start_handler_order() -> None:
    kernel = Kernel()
    await kernel.start(
        [
            _chain_member("dependent", requires=("base",)),
            _chain_member("zeta"),
            _chain_member("provider", provides=("base",)),
        ]
    )
    cold = await kernel.emit(Ping())

    assert await kernel.reload("provider") == ("provider", "dependent")

    assert cold == Ping(("provider", "zeta", "dependent"))
    assert await kernel.emit(Ping()) == cold


async def test_reload_without_on_drain_waits_for_handlers_not_resident_tasks() -> None:
    release = asyncio.Event()
    entered = asyncio.Event()
    setups = itertools.count(1)
    finished: list[int] = []
    residents: list[asyncio.Task[None]] = []

    async def setup(ctx: Context) -> None:
        number = next(setups)

        async def on_ping(event: Ping) -> Ping:
            entered.set()
            await release.wait()
            finished.append(number)
            return event

        async def resident() -> None:
            _ = await asyncio.Event().wait()

        ctx.on(Ping, on_ping)
        residents.append(ctx.spawn(resident()))

    kernel = Kernel()
    await kernel.start([PluginSpec("busy", setup)])
    emitting = asyncio.create_task(kernel.emit(Ping()))
    await entered.wait()
    reloading = asyncio.create_task(kernel.reload("busy"))
    await asyncio.sleep(0.01)
    assert not reloading.done()

    release.set()
    assert await asyncio.wait_for(reloading, 1) == ("busy",)
    _ = await emitting
    assert finished == [1]
    assert residents[0].cancelled()
    assert not residents[1].done()
    _ = await kernel.stop()


async def test_reload_waits_for_a_watch_handler_in_flight() -> None:
    release = asyncio.Event()
    entered = asyncio.Event()
    seen: list[str] = []

    async def setup(ctx: Context) -> None:
        async def record(event: Ping) -> None:
            entered.set()
            await release.wait()
            seen.append("delivered")

        ctx.watch(Ping, record)

    kernel = Kernel()
    await kernel.start([PluginSpec("observer", setup)])
    _ = await kernel.emit(Ping())
    await entered.wait()

    # The busy watcher holds the drain: the reload times out, nothing changes.
    with pytest.raises(KernelError, match="排空"):
        _ = await kernel.reload("observer", timeout=0.05)
    assert seen == []

    release.set()
    assert await asyncio.wait_for(kernel.reload("observer"), 1) == ("observer",)
    assert seen == ["delivered"]


async def test_reload_runs_on_drain_before_disposing_the_old_instance() -> None:
    steps: list[str] = []
    setups = itertools.count(1)

    async def setup(ctx: Context) -> None:
        number = next(setups)
        steps.append(f"setup {number}")

        async def drain() -> None:
            steps.append(f"drain {number}")

        ctx.on_drain(drain)
        ctx.effect(lambda: steps.append(f"dispose {number}"))

    kernel = Kernel()
    await kernel.start([PluginSpec("plugin", setup)])
    _ = await kernel.reload("plugin")

    assert steps == ["setup 1", "drain 1", "dispose 1", "setup 2"]


async def test_drain_timeout_abandons_the_reload_and_keeps_the_old_instance() -> None:
    stuck = asyncio.Event()
    disposed: list[str] = []

    async def setup(ctx: Context) -> None:
        ctx.provide(SERVICE, "old")

        async def wait() -> None:
            _ = await stuck.wait()

        ctx.on_drain(wait)
        ctx.effect(lambda: disposed.append("old"))

    kernel = Kernel()
    await kernel.start([PluginSpec("slow", setup, provides=("service",))])

    with pytest.raises(KernelError) as aborted:
        _ = await kernel.reload("slow", timeout=0.01)

    assert aborted.value.diagnostic.code == "drain_timeout"
    assert "保留旧实例" in aborted.value.diagnostic.reason
    assert aborted.value.plugin_ids == ("slow",)
    status = kernel.status("slow")
    assert status is not None and status.state == "ACTIVE"
    assert kernel.get(SERVICE) == "old"
    assert disposed == []
    stuck.set()


@pytest.mark.parametrize(
    "fields", [{"channels": True}, {"hot_reload": False}], ids=["channels", "no_hot"]
)
async def test_reload_closure_with_a_restart_only_plugin_is_refused_whole(
    fields: dict[str, bool],
) -> None:
    disposed: list[str] = []

    async def provider(ctx: Context) -> None:
        ctx.provide(SERVICE, object())
        ctx.effect(lambda: disposed.append("provider"))

    kernel = Kernel()
    await kernel.start(
        [
            PluginSpec("provider", provider, provides=("service",)),
            PluginSpec("channel", _idle, requires=("service",), **fields),
        ]
    )

    with pytest.raises(KernelError) as refused:
        _ = await kernel.reload("provider")

    assert refused.value.plugin_ids == ("channel",)
    assert "需重启" in refused.value.diagnostic.reason
    assert disposed == []


async def test_next_get_after_reload_returns_the_new_provider_generation() -> None:
    generations = itertools.count(1)
    key = Key[Generation]("generation")
    seen_by_consumer: list[int] = []

    async def provider(ctx: Context) -> None:
        ctx.provide(key, Generation(next(generations)))

    async def consumer(ctx: Context) -> None:
        async def on_ping(event: Ping) -> Ping:
            current = ctx.get(key)
            seen_by_consumer.append(current.number if current else 0)
            return event

        ctx.on(Ping, on_ping)

    kernel = Kernel()
    await kernel.start(
        [
            PluginSpec("provider", provider, provides=("generation",)),
            PluginSpec("consumer", consumer, optional=("generation",)),
        ]
    )
    _ = await kernel.emit(Ping())
    # The optional consumer is reset with its provider (§8.2).
    assert await kernel.reload("provider") == ("provider", "consumer")
    _ = await kernel.emit(Ping())

    assert seen_by_consumer == [1, 2]
    assert kernel.get(key) == Generation(2)
