"""Turns queued danmaku into replies for one run generation (``run_id``).

One loop, so at most one external turn is in flight; ``ReplyPacer`` decides
when the next may start. A busy role is never waited for: the danmaku goes
back to the head of the queue and may expire there.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from shiori_sdk.external_turns import ExternalTurnMessage, ExternalTurns

from .bilibili_live_api import LiveRoom
from .live_clock import Clock, Wakeup
from .live_config import LiveConfig
from .live_output import LiveReplyOutcome, LiveReplyOutput
from .live_pacing import ReplyPacer
from .live_queue import DanmakuQueue, QueuedDanmaku
from .live_status import LiveCounter, LiveStatus

# The external-turn platform of Bilibili live rooms (the room id is the
# conversation id, so each room is its own external thread of the role).
LIVE_PLATFORM = "bilibili"
# A busy role is retried this often while the danmaku has not expired.
BUSY_RETRY_S = 1.0

logger = logging.getLogger(__name__)


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
        self.pacer = ReplyPacer(clock, lambda: config().reply_interval_seconds)
        self.generating = False

    def wake(self) -> None:
        """Re-evaluate now (a danmaku arrived or the timing changed)."""
        self._wakeup.set()

    def outcome(self, outcome: LiveReplyOutcome) -> None:
        """Take this generation's outcome; it releases the output wait."""
        self._status.output_finished(outcome)
        if self.pacer.finished(outcome.reply_id):
            self._wakeup.set()

    async def run(self) -> None:
        """Process the queue until cancelled."""
        while True:
            timeout = self._config().wait_timeout_seconds
            expired = self._queue.drop_expired(self._clock.now(), timeout)
            self._status.count(LiveCounter.EXPIRED, expired)
            delay, lost = self.pacer.wait_time()
            if lost is not None:
                self._status.output_lost(lost, "未收到直播回复输出结果")
            item = self._queue.pop() if delay == 0 else None
            if item is not None:
                await self._reply(item)
                continue
            # Sleep until pacing allows, the oldest item expires, or a wake.
            wait = delay if delay > 0 else None
            expiry = self._queue.next_expiry(timeout)
            if expiry is not None:
                until_expiry = expiry - self._clock.now()
                wait = until_expiry if wait is None else min(wait, until_expiry)
            await self._wakeup.wait(wait)

    async def _reply(self, item: QueuedDanmaku) -> None:
        reply_id, danmaku = uuid.uuid4().hex, item.danmaku
        if not self._still_bound():
            # The role must exist and be the pet's role before its turn; the
            # run then ends through its binding watch.
            self._status.generation_failed(reply_id, "桌宠角色已切换或停用")
            return
        # ``parse_danmaku`` and ``fetch_room`` guarantee every field is
        # non-blank, so a rejection here is a bug in this plugin.
        message = ExternalTurnMessage(
            role_id=self._role_id,
            platform=LIVE_PLATFORM,
            conversation_id=str(self._room.room_id),
            conversation_title=self._room.title,
            sender_id=str(danmaku.uid),
            sender_name=danmaku.uname,
            message_id=danmaku.message_id,
            text=danmaku.text,
        )
        self.generating = True
        try:
            result = await self._turns.submit(message)
        except Exception as error:
            # The role was checked just above and the platform is fixed, so
            # whatever the host raises is this turn failing to generate a reply;
            # one bad turn never ends the run.
            logger.exception("live reply generation failed")
            self._status.generation_failed(reply_id, f"回复生成失败: {error}")
            self.pacer.cool_down()
            return
        finally:
            self.generating = False
        if result.status == "busy":
            self._status.count(LiveCounter.BUSY)
            self._status.count(LiveCounter.EVICTED, self._queue.push_front(item))
            self.pacer.retry_after(BUSY_RETRY_S)
        elif result.status == "duplicate":
            self._status.count(LiveCounter.DUPLICATES)
        elif not result.reply.strip():
            self._status.generation_failed(reply_id, "角色回复为空")
            self.pacer.cool_down()
        elif not self._still_bound():
            # The run ends through its binding watch; this reply is dropped.
            self._status.generation_failed(reply_id, "桌宠角色已切换或停用")
        else:
            await self._show(reply_id, result.reply.strip())

    async def _show(self, reply_id: str, text: str) -> None:
        self._status.generated(reply_id)
        # Set before emitting: the outcome may arrive while ``show`` awaits.
        self.pacer.awaiting(reply_id)
        delivered = await self._output.show(
            role_id=self._role_id, reply_id=reply_id, run_id=self.run_id, text=text
        )
        if not delivered and self.pacer.finished(reply_id):
            self._status.output_lost(reply_id, "桌宠后台未接收直播回复")
