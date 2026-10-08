"""One live run of one role in one room: connection, dedupe, queue and replies.

A run keeps its connection and dedupe memory from start to stop. Processing
happens in generations: start and every resume begin a new ``run_id``; pause
and stop end the current one, which cancels its in-flight turn, clears the
queue and cancels its pet output. The pet keeps a cancelled ``run_id``
cancelled, so a late result of an ended generation can never be shown.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from shiori_sdk.external_turns import ExternalTurns

from .bilibili_credentials import BilibiliCredentials
from .bilibili_danmaku import Danmaku
from .bilibili_live_api import LiveRoom
from .bilibili_live_source import DanmakuSource, LiveIdentityRejected
from .bilibili_login import BilibiliLoginRequired
from .live_clock import Clock
from .live_config import LiveConfig
from .live_connection import LiveConnection
from .live_dedupe import SeenMessages
from .live_dispatch import ReplyDispatcher
from .live_output import LiveReplyOutcome, LiveReplyOutput
from .live_queue import DanmakuQueue, QueuedDanmaku
from .live_status import ConnectionState, LiveStatus, RunState

# How often a run re-checks that its role is still the pet's enabled role.
BINDING_CHECK_S = 2.0

logger = logging.getLogger(__name__)

type Spawn = Callable[[Coroutine[object, object, None], str], asyncio.Task[None]]


@dataclass(frozen=True)
class LiveSessionDeps:
    """Collaborators shared by every run; injectable for tests."""

    source: DanmakuSource
    turns: ExternalTurns
    output: LiveReplyOutput
    credentials: Callable[[str], Awaitable[BilibiliCredentials]]
    still_bound: Callable[[str], bool]
    clock: Clock
    spawn: Spawn


class LiveSession:
    """Lifecycle of one run; ``on_ended`` fires once when it stops for any reason."""

    def __init__(
        self,
        *,
        role_id: str,
        room: LiveRoom,
        buvid: str,
        config: LiveConfig,
        deps: LiveSessionDeps,
        on_ended: Callable[["LiveSession"], None],
    ) -> None:
        self.role_id = role_id
        self.config = config
        self.status = LiveStatus(role_id, room)
        self._room = room
        self._deps = deps
        self._on_ended = on_ended
        self._seen = SeenMessages()
        self._queue = DanmakuQueue()
        self._connection = LiveConnection(
            room_id=room.room_id,
            buvid=buvid,
            credentials=lambda: deps.credentials(role_id),
            source=deps.source,
            on_danmaku=self._admit,
            status=self.status,
            clock=deps.clock,
        )
        self._tasks: list[asyncio.Task[None]] = []
        self._dispatcher: ReplyDispatcher | None = None
        self._dispatch_task: asyncio.Task[None] | None = None
        self._ended = False

    def start(self) -> None:
        """Begin connecting, watching the binding and processing."""
        self._tasks = [
            self._spawn(self._connect, "live-connection"),
            self._spawn(self._watch_binding, "live-binding"),
        ]
        self._begin_generation()

    async def pause(self) -> None:
        """Stop processing and output now; danmaku arriving meanwhile are dropped."""
        if self.status.state is not RunState.RUNNING:
            raise ValueError("直播互动未在运行")
        self.status.state = RunState.PAUSED
        await self._end_generation()

    def resume(self) -> None:
        """Process again, only danmaku that arrive from now on."""
        if self.status.state is not RunState.PAUSED:
            raise ValueError("直播互动未暂停")
        self.status.state = RunState.RUNNING
        self._begin_generation()

    async def stop(self, reason: str) -> None:
        """End the run: release the connection, cancel processing and output."""
        if self._ended:
            return
        self._ended = True
        current = asyncio.current_task()
        others = [task for task in self._tasks if task is not current]
        for task in others:
            task.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        await self._end_generation()
        self.status.state = RunState.STOPPED
        if self.status.connection is not ConnectionState.LOGIN_INVALID:
            self.status.connection = ConnectionState.CLOSED
        self.status.stop_reason = reason
        self._on_ended(self)

    def apply_config(self, config: LiveConfig) -> None:
        """Take new timing at once; a changed room applies to the next run."""
        self.config = config
        if self._dispatcher is not None:
            self._dispatcher.wake()

    def outcome(self, outcome: LiveReplyOutcome) -> None:
        """Route a pet outcome; ended generations only update the record."""
        dispatcher = self._dispatcher
        if dispatcher is not None and outcome.run_id == dispatcher.run_id:
            dispatcher.outcome(outcome)
        else:
            self.status.output_finished(outcome)

    def snapshot(self) -> dict[str, Any]:
        """Status plus the queue and in-flight facts."""
        dispatcher = self._dispatcher
        return self.status.snapshot(
            queue_length=len(self._queue),
            generating=dispatcher is not None and dispatcher.generating,
            output_pending=dispatcher is not None and dispatcher.output_pending,
        )

    def _admit(self, danmaku: Danmaku) -> None:
        if not self._seen.first_sight(danmaku.message_id):
            self.status.count("redelivered")
            return
        self.status.count("received")
        if self._dispatcher is None:
            return
        arrival = QueuedDanmaku(danmaku, self._deps.clock.now())
        self.status.count("evicted", self._queue.push(arrival))
        self._dispatcher.wake()

    def _begin_generation(self) -> None:
        run_id = uuid.uuid4().hex
        self.status.run_id = run_id
        self._dispatcher = ReplyDispatcher(
            run_id=run_id,
            role_id=self.role_id,
            room=self._room,
            queue=self._queue,
            config=lambda: self.config,
            turns=self._deps.turns,
            output=self._deps.output,
            still_bound=lambda: self._deps.still_bound(self.role_id),
            status=self.status,
            clock=self._deps.clock,
        )
        self._dispatch_task = self._spawn(self._dispatcher.run, "live-dispatch")
        self._tasks.append(self._dispatch_task)

    async def _end_generation(self) -> None:
        dispatcher, task = self._dispatcher, self._dispatch_task
        self._dispatcher = self._dispatch_task = None
        self._queue.clear()
        if task is None or dispatcher is None:
            return
        self._tasks.remove(task)
        if task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._deps.output.cancel(dispatcher.run_id)

    async def _connect(self) -> None:
        try:
            await self._connection.run()
        except (BilibiliLoginRequired, LiveIdentityRejected) as error:
            await self.stop(f"B 站登录不可用: {error}")

    async def _watch_binding(self) -> None:
        while True:
            await self._deps.clock.sleep(BINDING_CHECK_S)
            if not self._deps.still_bound(self.role_id):
                await self.stop("桌宠角色已切换或停用")
                return

    def _spawn(
        self, work: Callable[[], Awaitable[None]], name: str
    ) -> asyncio.Task[None]:
        return self._deps.spawn(self._guard(work), name)

    async def _guard(self, work: Callable[[], Awaitable[None]]) -> None:
        """A bug in any run task ends the run visibly instead of hanging it.

        ``work`` is created inside the task, so a task cancelled before it
        first runs leaves no never-awaited coroutine behind.
        """
        try:
            await work()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("live run task failed")
            self.status.fail(f"直播运行异常: {error}")
            await self.stop(f"直播运行异常: {error}")
