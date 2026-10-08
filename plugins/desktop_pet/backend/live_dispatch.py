"""Turns queued danmaku into replies for one run generation (``run_id``).

One loop, so at most one external turn is in flight; the next reply is only
generated after the previous one's output outcome arrived (or its safety
timeout passed) and the reply interval elapsed. A busy role is never waited
for: the danmaku goes back to the head of the queue and may expire there.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from shiori_sdk.external_turns import ExternalTurnMessage, ExternalTurns

from .bilibili_live_api import LiveRoom
from .live_clock import Clock, Wakeup
from .live_config import LiveConfig
from .live_output import LiveReplyOutcome, LiveReplyOutput
from .live_queue import DanmakuQueue, QueuedDanmaku
from .live_status import LiveStatus

LIVE_PLATFORM = "bilibili"
# A busy role is retried this often while the danmaku has not expired.
BUSY_RETRY_S = 1.0
# Upper bound on one reply's bubble + speech before the next may start.
OUTPUT_TIMEOUT_S = 120.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PendingOutput:
    reply_id: str
    deadline: float


class ReplyDispatcher:
    """The reply loop of one generation; cancelling its task stops everything."""

    def __init__(
        self,
        *,
        run_id: str,
        role_id: str,
        room: LiveRoom,
        queue: DanmakuQueue,
        config: Callable[[], LiveConfig],
        turns: ExternalTurns,
        output: LiveReplyOutput,
        still_bound: Callable[[], bool],
        status: LiveStatus,
        clock: Clock,
    ) -> None:
        self.run_id = run_id
        self._role_id = role_id
        self._room = room
        self._queue = queue
        self._config = config
        self._turns = turns
        self._output = output
        self._still_bound = still_bound
        self._status = status
        self._clock = clock
        self._wakeup = Wakeup(clock)
        self._pending: _PendingOutput | None = None
        self._ready_at = 0.0
        self.generating = False

    @property
    def output_pending(self) -> bool:
        """Whether a shown reply still awaits its outcome."""
        return self._pending is not None

    def wake(self) -> None:
        """Re-evaluate now (a danmaku arrived or the timing changed)."""
        self._wakeup.set()

    def outcome(self, outcome: LiveReplyOutcome) -> None:
        """Take this generation's outcome; it releases the output wait."""
        self._status.output_finished(outcome)
        if self._pending is not None and self._pending.reply_id == outcome.reply_id:
            self._finish_output()
            self._wakeup.set()

    async def run(self) -> None:
        """Process the queue until cancelled."""
        while True:
            now = self._clock.now()
            timeout = self._config().wait_timeout_seconds
            self._status.count("expired", self._queue.drop_expired(now, timeout))
            delay = self._blocked_for(now)
            if delay == 0:
                item = self._queue.pop()
                assert item is not None
                await self._reply(item)
                continue
            expiry = self._queue.next_expiry(timeout)
            if expiry is not None:
                delay = expiry - now if delay is None else min(delay, expiry - now)
            await self._wakeup.wait(delay)

    def _blocked_for(self, now: float) -> float | None:
        """0 when a danmaku can be taken now, else how long to wait (None: idle)."""
        if self._pending is not None:
            if now < self._pending.deadline:
                return self._pending.deadline - now
            self._status.output_lost(self._pending.reply_id, "未收到直播回复输出结果")
            self._finish_output()
        if now < self._ready_at:
            return self._ready_at - now
        return 0 if len(self._queue) else None

    async def _reply(self, item: QueuedDanmaku) -> None:
        reply_id = uuid.uuid4().hex
        danmaku = item.danmaku
        self.generating = True
        try:
            result = await self._turns.submit(
                ExternalTurnMessage(
                    role_id=self._role_id,
                    platform=LIVE_PLATFORM,
                    conversation_id=str(self._room.room_id),
                    conversation_title=self._room.title,
                    sender_id=str(danmaku.uid),
                    sender_name=danmaku.uname,
                    message_id=danmaku.message_id,
                    text=danmaku.text,
                )
            )
        except Exception as error:  # one failed generation must not end the run
            logger.exception("live reply generation failed")
            self._status.generation_failed(reply_id, f"回复生成失败: {error}")
            self._cool_down()
            return
        finally:
            self.generating = False
        if result.status == "busy":
            self._status.count("busy")
            self._status.count("evicted", self._queue.push_front(item))
            self._ready_at = self._clock.now() + BUSY_RETRY_S
            return
        if result.status == "duplicate":
            self._status.count("duplicates")
            return
        text = result.reply.strip()
        if not text:
            self._status.generation_failed(reply_id, "角色回复为空")
            self._cool_down()
            return
        if not self._still_bound():
            # The run ends through its binding watchdog; this reply is dropped.
            self._status.generation_failed(reply_id, "桌宠角色已切换或停用")
            return
        await self._show(reply_id, text)

    async def _show(self, reply_id: str, text: str) -> None:
        self._status.generated(reply_id)
        # Set before emitting: the outcome may arrive while ``show`` awaits.
        self._pending = _PendingOutput(reply_id, self._clock.now() + OUTPUT_TIMEOUT_S)
        delivered = await self._output.show(
            role_id=self._role_id, reply_id=reply_id, run_id=self.run_id, text=text
        )
        if not delivered and self._pending is not None:
            self._status.output_lost(reply_id, "桌宠后台未接收直播回复")
            self._finish_output()

    def _finish_output(self) -> None:
        self._pending = None
        self._cool_down()

    def _cool_down(self) -> None:
        self._ready_at = self._clock.now() + self._config().reply_interval_seconds
