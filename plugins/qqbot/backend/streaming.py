from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from bus.events_lifecycle import StreamDeltaReady, TurnCancelled, TurnStarted

from .formatting import (
    CHANNEL,
    LIVE_STREAM_MIN_INTERVAL_S,
    format_turn_live,
)
from .stream_delivery import _LiveTurnKey, _StreamDeliveryMixin, _StreamState

logger = logging.getLogger(__name__)


class _StreamingMixin(_StreamDeliveryMixin):
    """Owns event-driven QQBot live preview state and task coordination."""

    async def _on_turn_started(self, event: TurnStarted) -> None:
        if event.channel != CHANNEL:
            return
        # The final reply can still be queued when the next turn starts. Stop
        # old refreshes without discarding the old turn's acknowledged identity.
        for key in set(self._live_states) | set(self._live_tasks_by_turn):
            if key[0] == event.session_key:
                await self._finish_live_tasks(key)
        key = (event.session_key, event.chat_id, event.external_message_id)
        await self._finish_live_tasks(key)
        self._clear_live_turn(key)

    async def _on_turn_cancelled(self, event: TurnCancelled) -> None:
        if event.channel != CHANNEL:
            return
        key = (event.session_key, event.chat_id, event.external_message_id)
        await self._finish_live_tasks(key)
        if self._bus is not None and self._bus.has_pending_outbound(
            CHANNEL, event.chat_id, event.external_message_id
        ):
            return
        try:
            state = self._live_states.get(key)
            if state is not None and state.stream_msg_id and not state.completed:
                await self._delete_message(state.openid, state.stream_msg_id)
        finally:
            self._clear_live_turn(key)

    async def _on_stream_delta(self, event: StreamDeltaReady) -> None:
        if event.channel != CHANNEL or not event.content_delta:
            return
        turn_key = (event.session_key, event.chat_id, event.external_message_id)
        stopped = self._live_stop_events.setdefault(turn_key, asyncio.Event())
        if stopped.is_set():
            return
        self._reply_buffers[turn_key] = (
            self._reply_buffers.get(turn_key, "") + event.content_delta
        )
        # One refresh per session at a time; it re-reads the buffer before sending.
        if any(not task.done() for task in self._live_tasks_by_turn.get(turn_key, ())):
            return
        self._start_live_task(
            turn_key,
            self._sync_live_message(turn_key, event.chat_id),
        )

    async def _sync_live_message(self, turn_key: _LiveTurnKey, chat_id: str) -> None:
        """Replaces the preview with the latest reply, at most once per interval.

        Loops until the buffer stops growing, so text that arrives while a
        request is in flight (for example right before a tool call) still
        reaches the preview without waiting for the final reply.
        """
        loop = asyncio.get_running_loop()
        stopped = self._live_stop_events.setdefault(turn_key, asyncio.Event())
        synced_length = -1
        while not stopped.is_set():
            if len(self._reply_buffers.get(turn_key, "")) == synced_length:
                return
            delay = self._live_next_at.get(turn_key, 0.0) - loop.time()
            if delay > 0:
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=delay)
                    return
                except TimeoutError:
                    pass
            reply = self._reply_buffers.get(turn_key, "")
            if len(reply) == synced_length:
                return
            synced_length = len(reply)
            self._live_next_at[turn_key] = loop.time() + LIVE_STREAM_MIN_INTERVAL_S
            text = format_turn_live(reply)
            if not text or not await self._send_live_stream(turn_key, chat_id, text):
                return

    async def _send_live_stream(
        self,
        turn_key: _LiveTurnKey,
        chat_id: str,
        text: str,
    ) -> bool:
        kind, openid = self._parse_chat_id(chat_id)
        if kind != "c2c":
            return False
        msg_id = turn_key[2] or self._last_c2c_msg_id.get(openid)
        if not msg_id:
            return False
        lock = self._live_locks.setdefault(turn_key, asyncio.Lock())
        async with lock:
            state = self._live_states.setdefault(
                turn_key,
                _StreamState(
                    openid=openid,
                    msg_id=msg_id,
                    msg_seq=self._next_msg_seq(),
                ),
            )
            if state.completed:
                return False
            if state.error is not None:
                return False
            try:
                await self._update_stream(state, text, terminal=False)
            except Exception as exc:
                logger.warning(
                    "[qqbot] 临时流式刷新失败 session=%s err=%s",
                    turn_key,
                    exc,
                )
                return False
            return True

    def _start_live_task(
        self, turn_key: _LiveTurnKey, coro: Coroutine[Any, Any, None]
    ) -> None:
        task = asyncio.create_task(coro)
        self._live_tasks.add(task)
        self._live_tasks_by_turn.setdefault(turn_key, set()).add(task)
        task.add_done_callback(lambda done: self._on_live_task_done(turn_key, done))

    def _on_live_task_done(
        self, turn_key: _LiveTurnKey, task: asyncio.Task[None]
    ) -> None:
        self._live_tasks.discard(task)
        tasks = self._live_tasks_by_turn.get(turn_key)
        if tasks is not None:
            tasks.discard(task)
            if not tasks:
                self._live_tasks_by_turn.pop(turn_key, None)
        if not task.cancelled() and task.exception() is not None:
            logger.debug("[qqbot] 临时流式状态刷新失败: %s", task.exception())

    async def _finish_live_tasks(self, turn_key: _LiveTurnKey) -> None:
        # Wake throttle-only waits, but let in-flight HTTP writes acknowledge
        # their message ID and index before terminal delivery or session reset.
        self._live_stop_events.setdefault(turn_key, asyncio.Event()).set()
        tasks = list(self._live_tasks_by_turn.get(turn_key, set()))
        if tasks:
            pending = asyncio.gather(*tasks, return_exceptions=True)
            try:
                await asyncio.shield(pending)
            except asyncio.CancelledError:
                await pending
                raise

    async def _drain_live_tasks(self) -> None:
        tasks = [task for task in self._live_tasks if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _clear_live_turn(self, turn_key: _LiveTurnKey) -> None:
        self._live_states.pop(turn_key, None)
        self._reply_buffers.pop(turn_key, None)
        self._live_next_at.pop(turn_key, None)
        self._live_stop_events.pop(turn_key, None)
        self._live_locks.pop(turn_key, None)
