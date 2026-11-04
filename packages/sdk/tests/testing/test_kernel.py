"""The kernel harness starts real plugins on stub services and awaits watchers."""

import asyncio
import itertools
from dataclasses import dataclass

import pytest

from shiori_sdk.kernel import Context, KernelError, KernelState, Key, PluginSpec
from shiori_sdk.testing.kernel import KernelHarness

CLOCK = Key[str]("clock")


@dataclass(frozen=True)
class Tick:
    at: str


async def test_idle_waits_for_watchers_fed_by_a_stub_service() -> None:
    seen: list[str] = []

    async def setup(ctx: Context) -> None:
        async def record(event: Tick) -> None:
            await asyncio.sleep(0.01)
            seen.append(f"{ctx.require(CLOCK)}:{event.at}")

        ctx.watch(Tick, record)

    harness = KernelHarness({CLOCK: "stub"})
    kernel = await harness.start(PluginSpec("ticker", setup, requires=("clock",)))
    _ = await kernel.emit(Tick("1"))
    assert seen == []

    await harness.idle()

    assert seen == ["stub:1"]
    assert await harness.stop() == []


SERVICE = Key[object]("service")


@dataclass(frozen=True)
class Ping:
    trail: tuple[str, ...] = ()


@dataclass(frozen=True)
class Generation:
    number: int


async def _idle(ctx: Context) -> None:
    return None


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
    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(
        _chain_member("dependent", requires=("base",)),
        _chain_member("zeta"),
        _chain_member("provider", provides=("base",)),
    )
    cold = await kernel.emit(Ping())

    assert await harness.reload("provider") == ("provider", "dependent")

    assert cold == Ping(("provider", "zeta", "dependent"))
    assert await kernel.emit(Ping()) == cold


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

    harness = KernelHarness()
    _ = await harness.start(PluginSpec("plugin", setup))
    _ = await harness.reload("plugin")

    assert steps == ["setup 1", "drain 1", "dispose 1", "setup 2"]


async def test_reload_timeout_propagates_without_replacing_the_old_closure() -> None:
    """The reload composition must not dispose or restart after drain fails."""
    release, drained = asyncio.Event(), asyncio.Event()
    steps: list[tuple[str, str]] = []
    provided = object()

    async def setup(ctx: Context) -> None:
        steps.append(("setup", ctx.plugin_id))
        if ctx.plugin_id == "provider":
            ctx.provide(SERVICE, provided)
        else:

            async def drain() -> None:
                _ = await release.wait()
                drained.set()

            ctx.on_drain(drain)
        ctx.effect(lambda: steps.append(("dispose", ctx.plugin_id)))

    harness = KernelHarness()
    kernel = await harness.start(
        PluginSpec("provider", setup, provides=("service",)),
        PluginSpec("consumer", setup, optional=("service",)),
    )
    scopes = {plugin_id: kernel.scope(plugin_id) for plugin_id in kernel.order()}
    try:
        with pytest.raises(KernelError) as aborted:
            _ = await harness.reload("provider", timeout=0.01)

        assert aborted.value.diagnostic.code == "drain_timeout"
        assert aborted.value.plugin_ids == ("consumer",)
        assert steps == [("setup", "provider"), ("setup", "consumer")]
        assert kernel.get(SERVICE) is provided
        for plugin_id, scope in scopes.items():
            assert kernel.scope(plugin_id) is scope
            status = kernel.status(plugin_id)
            assert status is not None and status.state is KernelState.ACTIVE
    finally:
        release.set()
        _ = await asyncio.wait_for(drained.wait(), timeout=1)
        _ = await harness.stop()


@pytest.mark.parametrize(
    "channels,hot_reload", [(True, True), (False, False)], ids=["channels", "no_hot"]
)
async def test_reload_closure_with_a_restart_only_plugin_is_refused_whole(
    channels: bool,
    hot_reload: bool,
) -> None:
    disposed: list[str] = []

    async def provider(ctx: Context) -> None:
        ctx.provide(SERVICE, object())
        ctx.effect(lambda: disposed.append("provider"))

    harness = KernelHarness()
    _ = await harness.start(
        PluginSpec("provider", provider, provides=("service",)),
        PluginSpec(
            "channel",
            _idle,
            requires=("service",),
            channels=channels,
            hot_reload=hot_reload,
        ),
    )

    with pytest.raises(KernelError) as refused:
        _ = await harness.reload("provider")

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

    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(
        PluginSpec("provider", provider, provides=("generation",)),
        PluginSpec("consumer", consumer, optional=("generation",)),
    )
    _ = await kernel.emit(Ping())
    # The optional consumer is reset with its provider (§8.2).
    assert await harness.reload("provider") == ("provider", "consumer")
    _ = await kernel.emit(Ping())

    assert seen_by_consumer == [1, 2]
    assert kernel.get(key) == Generation(2)


async def test_start_only_activates_requested_runnable_inactive_plugins() -> None:
    """An unrelated start must not retry a failure or execute a parked spec."""
    started: list[str] = []

    async def setup(ctx: Context) -> None:
        started.append(ctx.plugin_id)
        if ctx.plugin_id == "broken":
            raise RuntimeError("cannot start")

    harness = KernelHarness()
    active = PluginSpec("active", setup)
    broken = PluginSpec("broken", setup)
    _ = await harness.start(active, broken)
    active_scope = harness.kernel.scope("active")
    _ = await harness.kernel.plan([PluginSpec("parked", setup)])

    _ = await harness.start(active, PluginSpec("disabled", setup, runnable=False))
    _ = await harness.start()

    assert started == ["active", "broken"]
    assert harness.kernel.scope("active") is active_scope
    assert harness.kernel.status("parked") is None
    assert harness.kernel.status("disabled") is None
    _ = await harness.start(broken)
    assert started == ["active", "broken", "broken"]
    _ = await harness.stop()


async def test_stop_releases_dependents_first_and_returns_all_cleanup_errors() -> None:
    """One failed cleanup must not strand the provider or later resources."""
    disposed: list[str] = []
    errors = {name: RuntimeError(name) for name in ("provider", "consumer")}

    async def setup(ctx: Context) -> None:
        if ctx.plugin_id == "provider":
            ctx.provide(SERVICE, object())

        def dispose() -> None:
            disposed.append(ctx.plugin_id)
            raise errors[ctx.plugin_id]

        ctx.effect(dispose)

    harness = KernelHarness()
    kernel = await harness.start(
        PluginSpec("provider", setup, provides=("service",)),
        PluginSpec("consumer", setup, requires=("service",)),
    )

    assert await harness.stop() == [errors["consumer"], errors["provider"]]
    assert disposed == ["consumer", "provider"]
    assert kernel.get(SERVICE) is None
    assert await harness.stop() == []


async def test_reload_refuses_a_plugin_that_is_not_active() -> None:
    harness = KernelHarness()
    with pytest.raises(KernelError) as refused:
        _ = await harness.reload("missing")
    assert refused.value.diagnostic.code == "not_active"
    assert refused.value.plugin_ids == ("missing",)


@pytest.mark.parametrize("rebuild_harness", [False, True])
async def test_stop_releases_instances_excluded_by_a_later_plan(
    rebuild_harness: bool,
) -> None:
    """Duplicate-provider replanning must not leak the previously active scope."""
    disposed: list[str] = []

    async def provider(ctx: Context) -> None:
        ctx.provide(SERVICE, object())
        ctx.effect(lambda: disposed.append(ctx.plugin_id))

    harness = KernelHarness()
    kernel = await harness.start(PluginSpec("first", provider, provides=("service",)))
    _ = await harness.start(PluginSpec("second", provider, provides=("service",)))
    assert kernel.order() == ()
    assert kernel.get(SERVICE) is not None

    if rebuild_harness:
        harness = KernelHarness(kernel=kernel)

    assert await harness.stop() == []
    assert disposed == ["first"]
    assert kernel.get(SERVICE) is None


async def test_stop_uses_current_dependencies_after_incremental_starts() -> None:
    """An earlier optional consumer must keep its later provider during cleanup."""
    disposed: list[tuple[str, bool]] = []

    async def consumer(ctx: Context) -> None:
        ctx.effect(lambda: disposed.append(("consumer", ctx.get(SERVICE) is not None)))

    async def provider(ctx: Context) -> None:
        ctx.provide(SERVICE, object())
        ctx.effect(lambda: disposed.append(("provider", True)))

    harness = KernelHarness()
    _ = await harness.start(PluginSpec("consumer", consumer, optional=("service",)))
    _ = await harness.start(PluginSpec("provider", provider, provides=("service",)))

    assert await harness.stop() == []
    assert disposed == [("consumer", True), ("provider", True)]
    assert harness.kernel.get(SERVICE) is None
