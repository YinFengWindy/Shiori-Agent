"""Supervised run tasks: failures are reported, cancellation spares the caller."""

import asyncio

from plugins.desktop_pet.backend.live_tasks import TaskSupervisor


def spawn(work, *, name):
    return asyncio.create_task(work, name=name)


async def test_a_failing_task_is_reported_instead_of_dying_silently():
    failures: list[Exception] = []

    async def on_failure(error: Exception) -> None:
        failures.append(error)

    async def broken() -> None:
        raise KeyError("bug")

    tasks = TaskSupervisor(spawn, on_failure)
    await tasks.start(broken, "broken")
    assert [type(error) for error in failures] == [KeyError]


async def test_cancel_all_spares_the_calling_task_and_leaves_no_coroutine():
    async def on_failure(error: Exception) -> None:
        raise AssertionError(error)

    tasks = TaskSupervisor(spawn, on_failure)
    ran: list[str] = []

    async def stopper() -> None:
        await tasks.cancel_all()
        ran.append("stopper finished")

    async def forever() -> None:
        await asyncio.Event().wait()

    sleeper = tasks.start(forever, "forever")
    # Cancelled before it ever ran: its coroutine is never even created.
    never = tasks.start(forever, "never")
    await tasks.start(stopper, "stopper")
    assert ran == ["stopper finished"]
    assert sleeper.cancelled() and never.cancelled()
