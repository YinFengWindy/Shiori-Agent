from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from bus.events_lifecycle import StreamDeltaReady, TurnStarted

from .formatting import (
    CHANNEL,
    LIVE_STREAM_MIN_INTERVAL_S,
    format_turn_live,
)
from .stream_delivery import _StreamDeliveryMixin, _StreamState

logger = logging.getLogger(__name__)


class _StreamingMixin(_StreamDeliveryMixin):
    """Owns event-driven QQBot live preview state and task coordination."""

    async def _on_turn_started(self, event: TurnStarted) -> None:
        if event.channel != CHANNEL:
            return
        await self._finish_live_tasks(event.session_key)
        self._clear_live_session(event.session_key)

    async def _on_stream_delta(self, event: StreamDeltaReady) -> None:
        if event.channel != CHANNEL or not event.content_delta:
            return
        session_key = event.session_key
        stopped = self._live_stop_events.setdefault(session_key, asyncio.Event())
        if stopped.is_set():
            return
        self._reply_buffers[session_key] = (
            self._reply_buffers.get(session_key, "") + event.content_delta
        )
        # One refresh per session at a time; it re-reads the buffer before sending.
        if any(
            not task.done() for task in self._live_tasks_by_session.get(session_key, ())
        ):
            return
        self._start_live_task(
            session_key,
            self._sync_live_message(session_key, event.chat_id),
        )

    async def _sync_live_message(self, session_key: str, chat_id: str) -> None:
        """Replaces the preview with the latest reply, at most once per interval.

        Loops until the buffer stops growing, so text that arrives while a
        request is in flight (for example right before a tool call) still
        reaches the preview without waiting for the final reply.
        """
        loop = asyncio.get_running_loop()
        stopped = self._live_stop_events.setdefault(session_key, asyncio.Event())
        synced_length = -1
        while not stopped.is_set():
            if len(self._reply_buffers.get(session_key, "")) == synced_length:
                return
            delay = self._live_next_at.get(session_key, 0.0) - loop.time()
            if delay > 0:
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=delay)
                    return
                except TimeoutError:
                    pass
            reply = self._reply_buffers.get(session_key, "")
            if len(reply) == synced_length:
                return
            synced_length = len(reply)
            self._live_next_at[session_key] = loop.time() + LIVE_STREAM_MIN_INTERVAL_S
            text = format_turn_live(reply)
            if not text or not await self._send_live_stream(session_key, chat_id, text):
                return

    async def _send_live_stream(
        self,
        session_key: str,
        chat_id: str,
        text: str,
    ) -> bool:
        kind, openid = self._parse_chat_id(chat_id)
        if kind != "c2c":
            return False
        msg_id = self._last_c2c_msg_id.get(openid)
        if not msg_id:
            return False
        lock = self._live_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            state = self._live_states.setdefault(
                session_key,
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
                    session_key,
                    exc,
                )
                return False
            return True

    def _start_live_task(
        self, session_key: str, coro: Coroutine[Any, Any, None]
    ) -> None:
        task = asyncio.create_task(coro)
        self._live_tasks.add(task)
        self._live_tasks_by_session.setdefault(session_key, set()).add(task)
        task.add_done_callback(lambda done: self._on_live_task_done(session_key, done))

    def _on_live_task_done(self, session_key: str, task: asyncio.Task[None]) -> None:
        self._live_tasks.discard(task)
        tasks = self._live_tasks_by_session.get(session_key)
        if tasks is not None:
            tasks.discard(task)
            if not tasks:
                self._live_tasks_by_session.pop(session_key, None)
        if not task.cancelled() and task.exception() is not None:
            logger.debug("[qqbot] 临时流式状态刷新失败: %s", task.exception())

    async def _finish_live_tasks(self, session_key: str) -> None:
        # Wake throttle-only waits, but let in-flight HTTP writes acknowledge
        # their message ID and index before terminal delivery or session reset.
        self._live_stop_events.setdefault(session_key, asyncio.Event()).set()
        tasks = list(self._live_tasks_by_session.get(session_key, set()))
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

    def _clear_live_session(self, session_key: str) -> None:
        self._live_states.pop(session_key, None)
        self._reply_buffers.pop(session_key, None)
        self._live_next_at.pop(session_key, None)
        self._live_stop_events.pop(session_key, None)
        self._live_locks.pop(session_key, None)
