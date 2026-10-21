"""Pacing cancellation never releases another role operation's gate."""

import asyncio

import pytest

from core.roles.turn_gate import role_turn_gate, wait_outside_role_gate


@pytest.mark.parametrize("during_reacquire", [False, True])
async def test_cancel_suspended_owner_preserves_current_holder(during_reacquire):
    lock = asyncio.Lock()
    paused, resume, other_entered, other_release = (asyncio.Event() for _ in range(4))

    async def pause():
        paused.set()
        await resume.wait()

    async def first():
        async with role_turn_gate(lock):
            await wait_outside_role_gate(pause)
            pytest.fail("cancelled work must never resume")

    async def other():
        async with role_turn_gate(lock):
            other_entered.set()
            await other_release.wait()
            assert lock.locked()

    first_task = asyncio.create_task(first())
    await paused.wait()
    other_task = asyncio.create_task(other())
    await other_entered.wait()
    if during_reacquire:
        resume.set()
        await asyncio.sleep(0)
    first_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_task
    assert lock.locked()
    other_release.set()
    await other_task
    assert not lock.locked()


async def test_cancelled_pacing_reacquires_before_protected_accounting():
    from core.common.cancellation import finish_started
    from core.roles.turn_gate import reacquire_role_gate

    lock = asyncio.Lock()
    paused, other_entered, other_release = (asyncio.Event() for _ in range(3))
    accounted = []

    async def pause():
        paused.set()
        await asyncio.Event().wait()

    async def cleanup():
        await reacquire_role_gate()
        assert lock.locked()
        accounted.append("once")

    async def first():
        async with role_turn_gate(lock):
            try:
                await wait_outside_role_gate(pause)
            finally:
                await finish_started(cleanup())

    async def other():
        async with role_turn_gate(lock):
            other_entered.set()
            await other_release.wait()

    task = asyncio.create_task(first())
    await paused.wait()
    other_task = asyncio.create_task(other())
    await other_entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert accounted == [] and lock.locked()
    other_release.set()
    await other_task
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert accounted == ["once"]
    assert not lock.locked()
