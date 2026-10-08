"""The current processing generation of a run and its reply loop.

Start and every resume begin a generation with a fresh ``run_id``; pause and
stop end it, which cancels its in-flight turn, clears the queue and cancels
the pet output of that ``run_id``. The pet keeps a cancelled ``run_id``
cancelled, so a late result of an ended generation is never shown.

Host caveat: cancelling an in-flight ``submit`` cannot undo a turn the host
already committed. A cancel that lands after the host stored the danmaku and
the reply in the room thread (the turn's end, before ``submit`` returns) leaves
both stored but never shown or spoken; a resubmit would be ``duplicate``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .bilibili_danmaku import Danmaku
from .live_clock import Clock
from .live_dispatch import ReplyDispatcher
from .live_output import LiveReplyOutcome, LiveReplyOutput
from .live_queue import DanmakuQueue, QueuedDanmaku
from .live_status import LiveCounter, LiveStatus
from .live_tasks import TaskSupervisor


@dataclass(frozen=True)
class Generation:
    """A detached generation, still to be closed."""

    dispatcher: ReplyDispatcher
    task: asyncio.Task[None]


class LiveGenerations:
    """Owns the queue and at most one active generation."""

    def __init__(
        self,
        *,
        dispatcher: Callable[[str], ReplyDispatcher],
        queue: DanmakuQueue,
        tasks: TaskSupervisor,
        output: LiveReplyOutput,
        status: LiveStatus,
        clock: Clock,
    ) -> None:
        self._dispatcher = dispatcher
        self._queue = queue
        self._tasks = tasks
        self._output = output
        self._status = status
        self._clock = clock
        self._current: Generation | None = None

    def begin(self) -> None:
        """Start a generation with a new ``run_id``."""
        run_id = uuid.uuid4().hex
        self._status.run_id = run_id
        dispatcher = self._dispatcher(run_id)
        task = self._tasks.start(dispatcher.run, "live-dispatch")
        self._current = Generation(dispatcher, task)

    def detach(self) -> Generation | None:
        """End processing now (synchronously); ``close`` finishes the job."""
        generation, self._current = self._current, None
        self._queue.clear()
        return generation

    async def close(self, generation: Generation | None) -> None:
        """Cancel the detached generation's turn and its pet output."""
        if generation is None:
            return
        await self._tasks.cancel(generation.task)
        await self._output.cancel(generation.dispatcher.run_id)

    def admit(self, danmaku: Danmaku) -> None:
        """Queue a new danmaku; dropped while no generation runs (paused)."""
        if self._current is None:
            self._status.count(LiveCounter.DROPPED_PAUSED)
            return
        arrival = QueuedDanmaku(danmaku, self._clock.now())
        self._status.count(LiveCounter.EVICTED, self._queue.push(arrival))
        self._current.dispatcher.wake()

    def outcome(self, outcome: LiveReplyOutcome) -> None:
        """Route a pet outcome; ended generations only update the record."""
        current = self._current
        if current is not None and outcome.run_id == current.dispatcher.run_id:
            current.dispatcher.outcome(outcome)
        else:
            self._status.output_finished(outcome)

    def wake(self) -> None:
        """Make the active loop re-read its timing."""
        if self._current is not None:
            self._current.dispatcher.wake()

    def facts(self) -> dict[str, Any]:
        """Queue and in-flight facts for the status."""
        dispatcher = None if self._current is None else self._current.dispatcher
        return {
            "queue_length": len(self._queue),
            "generating": dispatcher is not None and dispatcher.generating,
            "output_pending": dispatcher is not None
            and dispatcher.pacer.output_pending,
        }
