"""Scope release order and default draining."""

import asyncio

import pytest

from shiori_sdk.kernel import Scope


async def test_close_releases_subscriptions_then_tasks_then_effects_lifo() -> None:
    scope = Scope("demo")
    order: list[str] = []

    async def worker() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            order.append("task cancelled")
            raise

    _ = scope.effect(lambda: order.append("effect 1"))
    scope.subscribe(lambda: order.append("subscription 1"))
    _ = scope.spawn(worker())
    _ = scope.effect(lambda: order.append("effect 2"))
    scope.subscribe(lambda: order.append("subscription 2"))
    await asyncio.sleep(0)

    assert await scope.close() == []

    assert order == [
        "subscription 2",
        "subscription 1",
        "task cancelled",
        "effect 2",
        "effect 1",
    ]
    with pytest.raises(RuntimeError, match="作用域已释放"):
        _ = scope.effect(lambda: None)


async def test_failing_effect_is_reported_and_the_rest_still_runs() -> None:
    scope = Scope("demo")
    closed: list[str] = []
    broken = ValueError("broken")

    def fail() -> None:
        raise broken

    _ = scope.effect(lambda: closed.append("first"))
    _ = scope.effect(fail)

    assert await scope.close() == [broken]
    assert closed == ["first"]


async def test_drain_waits_for_handlers_in_flight_then_runs_on_drain() -> None:
    scope = Scope("demo")
    release = asyncio.Event()
    steps: list[str] = []

    async def handler() -> None:
        with scope.busy():
            await release.wait()
            steps.append("handler done")

    async def on_drain() -> None:
        steps.append("on_drain")

    resident = scope.spawn(asyncio.Event().wait())
    running = asyncio.create_task(handler())
    scope.drainers.append(on_drain)
    await asyncio.sleep(0)
    draining = asyncio.create_task(scope.drain())
    await asyncio.sleep(0.01)
    assert not draining.done()

    release.set()
    await asyncio.wait_for(draining, 1)

    # The resident task is not waited for; only ``close`` ends it.
    assert steps == ["handler done", "on_drain"]
    assert not resident.done()
    await running
    _ = await scope.close()
    assert resident.cancelled()
