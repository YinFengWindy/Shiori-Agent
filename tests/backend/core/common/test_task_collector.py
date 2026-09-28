import asyncio
import threading

from core.common.task_collector import TaskCollector


def test_drain_returns_when_tasks_finished_before_their_callbacks_ran():
    async def scenario() -> None:
        collector = TaskCollector("test")

        async def work() -> None:
            return None

        _ = collector.spawn(work(), name="work")
        # The task finishes here; its done callback is only scheduled.
        await asyncio.sleep(0)
        await collector.drain()

    # A spinning drain never yields, so no in-loop timeout could fire; run it
    # on a daemon thread and bound the wait from outside.
    runner = threading.Thread(target=asyncio.run, args=(scenario(),), daemon=True)
    runner.start()
    runner.join(timeout=5)

    assert not runner.is_alive()
