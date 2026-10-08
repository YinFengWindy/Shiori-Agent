"""One live run of one role in one room: connection, dedupe and generations.

A run keeps its connection and dedupe memory from start to stop; processing
happens in generations (``live_generation``). Every state change happens
synchronously before the first await, and a stopping run refuses pause and
resume, so no generation can start once stop began — whether the stop came
from the user, the binding watch, a refused connection or a failed task.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from shiori_sdk.external_turns import ExternalTurns

from .bilibili_credentials import BilibiliCredentials
from .bilibili_danmaku import Danmaku
from .bilibili_live_api import LiveRoom
from .bilibili_live_stream import DanmakuSource
from .live_binding import watch_binding
from .live_clock import Clock
from .live_config import LiveConfig
from .live_connection import LiveConnection, LiveConnectionEnded
from .live_dedupe import SeenMessages
from .live_dispatch import ReplyDispatcher
from .live_generation import LiveGenerations
from .live_output import LiveReplyOutcome, LiveReplyOutput
from .live_queue import DanmakuQueue
from .live_status import ConnectionState, LiveCounter, LiveStatus, RunState
from .live_tasks import SpawnTask, TaskSupervisor

# Connection states that already explain why the run ended.
_TERMINAL_CONNECTION = {ConnectionState.REJECTED, ConnectionState.LOGIN_INVALID}


@dataclass(frozen=True)
class LiveSessionDeps:
    """Collaborators shared by every run; injectable for tests."""

    source: DanmakuSource
    turns: ExternalTurns
    output: LiveReplyOutput
    credentials: Callable[[str], Awaitable[BilibiliCredentials]]
    still_bound: Callable[[str], bool]
    clock: Clock
    spawn: SpawnTask


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
        self._deps = deps
        self._on_ended = on_ended
        self._closing = False
        self._seen = SeenMessages()
        self._tasks = TaskSupervisor(deps.spawn, self._failed)
        queue = DanmakuQueue()
        self._generations = LiveGenerations(
            dispatcher=lambda run_id: ReplyDispatcher(
                run_id=run_id,
                role_id=role_id,
                room=room,
                queue=queue,
                config=lambda: self.config,
                turns=deps.turns,
                output=deps.output,
                still_bound=lambda: deps.still_bound(role_id),
                status=self.status,
                clock=deps.clock,
            ),
            queue=queue,
            tasks=self._tasks,
            output=deps.output,
            status=self.status,
            clock=deps.clock,
        )
        self._connection = LiveConnection(
            room_id=room.room_id,
            buvid=buvid,
            credentials=lambda: deps.credentials(role_id),
            source=deps.source,
            on_danmaku=self._admit,
            status=self.status,
            clock=deps.clock,
        )

    def start(self) -> None:
        """Begin connecting, watching the binding and processing."""
        self._tasks.start(self._connect, "live-connection")
        self._tasks.start(self._watch, "live-binding")
        self._generations.begin()

    async def pause(self) -> None:
        """Stop processing and output now; danmaku arriving meanwhile are dropped."""
        self._require(RunState.RUNNING, "直播互动未在运行")
        self.status.state = RunState.PAUSED
        await self._generations.close(self._generations.detach())

    def resume(self) -> None:
        """Process again, only danmaku that arrive from now on."""
        self._require(RunState.PAUSED, "直播互动未暂停")
        self.status.state = RunState.RUNNING
        self._generations.begin()

    async def stop(self, reason: str) -> None:
        """End the run: release the connection, cancel processing and output."""
        if self._closing:
            return
        self._closing = True
        self.status.state = RunState.STOPPED
        self.status.stop_reason = reason
        if self.status.connection not in _TERMINAL_CONNECTION:
            self.status.connection = ConnectionState.CLOSED
        generation = self._generations.detach()
        try:
            await self._tasks.cancel_all()
            await self._generations.close(generation)
        finally:
            # The engine must learn the run ended even if cleanup raised.
            self._on_ended(self)

    def apply_config(self, config: LiveConfig) -> None:
        """Take new timing at once; a changed room applies to the next run."""
        self.config = config
        self._generations.wake()

    def outcome(self, outcome: LiveReplyOutcome) -> None:
        """Route a pet outcome to the generation it belongs to."""
        self._generations.outcome(outcome)

    def snapshot(self) -> dict[str, Any]:
        """Status plus the queue and in-flight facts."""
        return self.status.snapshot(**self._generations.facts())

    def _require(self, state: RunState, message: str) -> None:
        if self._closing or self.status.state is not state:
            raise ValueError(message)

    def _admit(self, danmaku: Danmaku) -> None:
        if not self._seen.first_sight(danmaku.message_id):
            self.status.count(LiveCounter.REDELIVERED)
            return
        self.status.count(LiveCounter.RECEIVED)
        self._generations.admit(danmaku)

    async def _connect(self) -> None:
        try:
            await self._connection.run()
        except LiveConnectionEnded as error:
            if error.state is ConnectionState.LOGIN_INVALID:
                await self.stop(f"B 站登录不可用: {error}")
            else:
                await self.stop(f"B 站拒绝了直播连接: {error}")

    async def _watch(self) -> None:
        def still_bound() -> bool:
            return self._deps.still_bound(self.role_id)

        await watch_binding(
            self._deps.clock, still_bound, lambda: self.stop("桌宠角色已切换或停用")
        )

    async def _failed(self, error: Exception) -> None:
        await self.stop(f"直播运行异常: {error}")
