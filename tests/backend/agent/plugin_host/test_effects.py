from __future__ import annotations

import asyncio

import pytest

from agent.plugin_host.effects import EffectScope


@pytest.mark.asyncio
async def test_dispose_all_runs_in_reverse_order():
    scope = EffectScope("demo")
    order: list[str] = []
    scope.add("a", lambda: order.append("a"))
    scope.add("b", lambda: order.append("b"))

    async def dispose_c():
        order.append("c")

    scope.add("c", dispose_c)

    errors = await scope.dispose_all()
    assert errors == []
    assert order == ["c", "b", "a"]


@pytest.mark.asyncio
async def test_dispose_error_collected_without_blocking_rest():
    scope = EffectScope("demo")
    order: list[str] = []
    scope.add("ok-first", lambda: order.append("first"))

    def broken():
        raise RuntimeError("cleanup boom")

    scope.add("broken", broken)
    scope.add("ok-last", lambda: order.append("last"))

    errors = await scope.dispose_all()
    assert [str(e) for e in errors] == ["cleanup boom"]
    # 失败不阻断其余清理，逆序继续
    assert order == ["last", "first"]


@pytest.mark.asyncio
async def test_add_after_dispose_rejected():
    scope = EffectScope("demo")
    await scope.dispose_all()
    with pytest.raises(RuntimeError, match="已处置"):
        scope.add("late", lambda: None)


@pytest.mark.asyncio
async def test_labels_report_registration_order():
    scope = EffectScope("demo")
    scope.add("one", lambda: None)
    scope.add("two", lambda: None)
    assert scope.labels == ["one", "two"]


@pytest.mark.asyncio
async def test_subscription_cleanup_errors_do_not_skip_other_disposers():
    scope = EffectScope("demo")
    order = []
    scope.add("first", lambda: order.append("first"))
    scope.add_subscription("subscription", lambda: order.append("subscription"))

    def broken():
        raise ValueError("unsubscribe failed")

    scope.add_subscription("broken", broken)
    # An ordinary effect's label cannot move it into the subscription lane.
    scope.add("event:last", lambda: order.append("last"))
    assert scope.labels == ["first", "subscription", "broken", "event:last"]
    errors = await scope.dispose_all()
    assert [str(error) for error in errors] == ["unsubscribe failed"]
    assert order == ["subscription", "last", "first"]


@pytest.mark.asyncio
async def test_concurrent_disposal_waits_for_current_cleanup():
    scope = EffectScope("demo")
    entered, release = asyncio.Event(), asyncio.Event()

    async def close():
        entered.set()
        await release.wait()

    scope.add("close", close)
    first = asyncio.create_task(scope.dispose_all())
    await asyncio.wait_for(entered.wait(), timeout=2)
    second = asyncio.create_task(scope.dispose_all())
    try:
        await asyncio.sleep(0)
        assert not second.done()
        assert not scope.active
        with pytest.raises(RuntimeError, match="已处置"):
            scope.add("late", lambda: None)
    finally:
        release.set()
        assert await first == []
        assert await second == []


@pytest.mark.asyncio
async def test_cancelled_disposal_can_resume_remaining_cleanup():
    scope = EffectScope("demo")
    entered = asyncio.Event()
    closed = []

    async def blocking():
        entered.set()
        await asyncio.Event().wait()

    scope.add("remaining", lambda: closed.append("remaining"))
    scope.add("blocking", blocking)
    disposing = asyncio.create_task(scope.dispose_all())
    await asyncio.wait_for(entered.wait(), timeout=2)
    disposing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await disposing
    assert not scope.active
    assert await scope.dispose_all() == []
    assert closed == ["remaining"]
