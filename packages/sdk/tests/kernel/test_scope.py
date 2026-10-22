"""Scope release order and default draining."""

import asyncio

import pytest

from shiori_sdk.kernel import Scope, scope as scope_module


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


async def test_on_drain_runs_after_the_handlers_in_flight() -> None:
    scope = Scope("demo")
    release = asyncio.Event()
    steps: list[str] = []

    async def handler() -> None:
        with scope.busy():
            await release.wait()
            steps.append("handler done")

    async def on_drain() -> None:
        steps.append("on_drain")

    running = asyncio.create_task(handler())
    scope.drainers.append(on_drain)
    await asyncio.sleep(0)
    draining = asyncio.create_task(scope.drain())
    await asyncio.sleep(0.01)
    assert steps == []

    release.set()
    await asyncio.wait_for(draining, 1)
    await running
    assert steps == ["handler done", "on_drain"]


async def test_close_lets_watch_deliveries_finish_within_grace_then_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scope_module, "WATCH_GRACE", 0.05)
    scope = Scope("demo")
    delivered: list[str] = []

    async def quick() -> None:
        await asyncio.sleep(0.01)
        delivered.append("quick")

    async def stuck() -> None:
        await asyncio.Event().wait()

    finishing = scope.spawn(quick(), worker=True)
    hanging = scope.spawn(stuck(), worker=True)
    await asyncio.sleep(0)

    assert await scope.close() == []

    assert delivered == ["quick"]
    assert finishing.done() and not finishing.cancelled()
    assert hanging.cancelled()
