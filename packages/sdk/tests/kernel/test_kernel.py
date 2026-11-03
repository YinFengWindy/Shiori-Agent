"""Kernel lifecycle: failure propagation, reload closure, draining and providers."""

import asyncio
import itertools
from dataclasses import dataclass

import pytest

from shiori_sdk.kernel import (
    Context,
    KernelError,
    KernelState,
    Key,
    PluginDiagnostic,
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

    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(
        PluginSpec("provider", broken, provides=("service",)),
        PluginSpec("hard", hard, requires=("service",)),
        PluginSpec("soft", soft, optional=("service",)),
        PluginSpec("orphan", hard, requires=("nobody",)),
    )

    failed = kernel.status("provider")
    blocked = kernel.status("hard")
    assert failed is not None and failed.state is KernelState.FAILED
    assert failed.diagnostic is not None and "cannot start" in failed.diagnostic.reason
    assert blocked is not None and blocked.state is KernelState.BLOCKED
    # The two BLOCKED causes read differently: enable the provider vs install it.
    assert blocked.diagnostic is not None
    assert blocked.diagnostic.code == "dependency_unavailable"
    assert blocked.diagnostic.reason == "插件 hard 依赖的 service 未启用或加载失败"
    orphan = kernel.status("orphan")
    assert orphan is not None and orphan.diagnostic is not None
    assert orphan.diagnostic.code == "missing_dependency"
    assert orphan.diagnostic.reason == "插件 orphan 依赖的 nobody 不存在"
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


@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_failed_deactivation_preserves_cause_and_cleanup_outcome(
    cleanup_fails: bool,
) -> None:
    seen: list[PluginFailed | PluginStopped] = []
    cleanup_error = RuntimeError("cleanup failed")

    async def observe(ctx: Context) -> None:
        async def record(event: PluginFailed | PluginStopped) -> None:
            seen.append(event)

        ctx.watch(PluginFailed, record)
        ctx.watch(PluginStopped, record)

    async def worker(ctx: Context) -> None:
        ctx.provide(SERVICE, object())

        def dispose() -> None:
            if cleanup_fails:
                raise cleanup_error

        ctx.effect(dispose)

    harness = KernelHarness()
    kernel = await harness.start(
        PluginSpec("observe", observe),
        PluginSpec("worker", worker, provides=("service",)),
    )
    failure = PluginDiagnostic(
        "renderer_ui_failed", "ui", "frontend.entry", "renderer failed", state="FAILED"
    )
    error = RuntimeError("renderer failed")
    errors = await kernel.deactivate("worker", failure=failure, error=error)
    await harness.idle()

    status = kernel.status("worker")
    assert status is not None and status.state is KernelState.FAILED
    assert status.diagnostic is failure and status.error is error
    assert errors == ([cleanup_error] if cleanup_fails else [])
    assert status.cleanup_errors == tuple(errors)
    assert kernel.get(SERVICE) is None
    assert seen == [PluginFailed("worker", failure)]
    assert await kernel.deactivate("worker", failure=failure, error=error) == []
    await harness.idle()
    assert seen == [PluginFailed("worker", failure)]
    _ = await harness.stop()


async def test_repeated_activation_preserves_the_scope_during_setup() -> None:
    entered, finish = asyncio.Event(), asyncio.Event()
    provided = object()
    released: list[object] = []

    async def setup(ctx: Context) -> None:
        ctx.provide(SERVICE, provided)
        ctx.effect(lambda: released.append(provided))
        entered.set()
        await finish.wait()

    harness = KernelHarness()
    kernel = harness.kernel
    starting = asyncio.create_task(
        harness.start(PluginSpec("provider", setup, provides=("service",)))
    )
    await entered.wait()
    scope = kernel.scope("provider")
    try:
        with pytest.raises(KernelError) as refused:
            _ = await kernel.activate("provider")
        assert refused.value.diagnostic.code == "already_running"
        assert kernel.scope("provider") is scope
        assert kernel.get(SERVICE) is provided
    finally:
        finish.set()
        _ = await starting
        _ = await harness.stop()
    assert released == [provided]
    assert kernel.get(SERVICE) is None


async def test_require_and_provide_must_be_declared_in_the_manifest() -> None:
    async def sneaky(ctx: Context) -> None:
        ctx.require(SERVICE)

    async def overreach(ctx: Context) -> None:
        ctx.provide(SERVICE, object())

    harness = KernelHarness()
    kernel = harness.kernel
    kernel.provide(SERVICE, object())
    _ = await harness.start(PluginSpec("sneaky", sneaky), PluginSpec("over", overreach))

    for plugin_id in ("sneaky", "over"):
        status = kernel.status(plugin_id)
        assert status is not None and status.state is KernelState.FAILED
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


async def test_drain_without_on_drain_waits_for_handlers_not_resident_tasks() -> None:
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

    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(PluginSpec("busy", setup))
    emitting = asyncio.create_task(kernel.emit(Ping()))
    await entered.wait()
    draining = asyncio.create_task(kernel.drain(["busy"], timeout=1))
    await asyncio.sleep(0.01)
    assert not draining.done()

    release.set()
    await asyncio.wait_for(draining, 1)
    _ = await emitting
    assert finished == [1]
    assert not residents[0].done()
    _ = await harness.stop()
    assert residents[0].cancelled()


async def test_drain_waits_for_a_watch_handler_in_flight() -> None:
    release = asyncio.Event()
    entered = asyncio.Event()
    seen: list[str] = []

    async def setup(ctx: Context) -> None:
        async def record(event: Ping) -> None:
            entered.set()
            await release.wait()
            seen.append("delivered")

        ctx.watch(Ping, record)

    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(PluginSpec("observer", setup))
    _ = await kernel.emit(Ping())
    await entered.wait()

    # The busy watcher holds the drain: it times out without dropping delivery.
    with pytest.raises(KernelError, match="排空"):
        await kernel.drain(["observer"], timeout=0.05)
    assert seen == []

    release.set()
    await asyncio.wait_for(kernel.drain(["observer"], timeout=1), 1)
    assert seen == ["delivered"]
    _ = await harness.stop()


async def test_drain_timeout_keeps_the_old_instance() -> None:
    stuck = asyncio.Event()
    disposed: list[str] = []

    async def setup(ctx: Context) -> None:
        ctx.provide(SERVICE, "old")

        async def wait() -> None:
            _ = await stuck.wait()

        ctx.on_drain(wait)
        ctx.effect(lambda: disposed.append("old"))

    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(PluginSpec("slow", setup, provides=("service",)))

    with pytest.raises(KernelError) as aborted:
        await kernel.drain(["slow"], timeout=0.01)

    assert aborted.value.diagnostic.code == "drain_timeout"
    assert "保留旧实例" in aborted.value.diagnostic.reason
    assert aborted.value.plugin_ids == ("slow",)
    status = kernel.status("slow")
    assert status is not None and status.state is KernelState.ACTIVE
    assert kernel.get(SERVICE) == "old"
    assert disposed == []
    stuck.set()


async def test_start_does_not_activate_a_register_only_plugin() -> None:
    started: list[str] = []

    async def setup(ctx: Context) -> None:
        started.append(ctx.plugin_id)

    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(
        PluginSpec("untrusted", setup, runnable=False),
        PluginSpec("trusted", setup),
    )

    assert started == ["trusted"]
    trusted = kernel.status("trusted")
    assert trusted is not None and trusted.state is KernelState.ACTIVE
    assert kernel.status("untrusted") is None
    with pytest.raises(KernelError) as refused:
        _ = await kernel.activate("untrusted")
    assert refused.value.diagnostic.code == "not_runnable"
    assert started == ["trusted"]
    assert kernel.status("untrusted") is None


async def test_register_only_cycle_partner_blocks_as_not_enabled() -> None:
    failed: list[str] = []

    async def observe(ctx: Context) -> None:
        async def record(event: PluginFailed) -> None:
            failed.append(event.plugin_id)

        ctx.watch(PluginFailed, record)

    harness = KernelHarness()
    kernel = await harness.start(PluginSpec("observe", observe))
    _ = await harness.start(
        PluginSpec("enabled", _idle, requires=("b_key",), provides=("a_key",)),
        PluginSpec(
            "disabled",
            _idle,
            requires=("a_key",),
            provides=("b_key",),
            runnable=False,
        ),
    )
    await harness.idle()

    enabled = kernel.status("enabled")
    assert enabled is not None and enabled.state is KernelState.BLOCKED
    assert enabled.diagnostic is not None
    assert enabled.diagnostic.code == "dependency_unavailable"
    assert enabled.diagnostic.reason == "插件 enabled 依赖的 b_key 未启用或加载失败"
    assert kernel.status("disabled") is None
    assert failed == ["enabled"]


async def test_closure_takes_optional_consumers_only_for_a_reload() -> None:
    harness = KernelHarness()
    kernel = harness.kernel
    _ = await harness.start(
        _chain_member("provider", provides=("base",)),
        _chain_member("hard", requires=("base",)),
        PluginSpec("soft", _idle, optional=("base",)),
        _chain_member("other"),
    )

    assert set(kernel.closure("provider", optional=False)) == {"provider", "hard"}
    assert set(kernel.closure("provider", optional=True)) == {
        "provider",
        "hard",
        "soft",
    }
    # Dependents first: the provider is disposed last and set up first.
    assert kernel.closure("provider", optional=False)[-1] == "provider"
