from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

from bus.events_lifecycle import StreamDeltaReady, TurnStarted

from .formatting import (
    CHANNEL,
    LIVE_MAX_FAILURES,
    LIVE_STREAM_MIN_CHARS,
    LIVE_STREAM_MIN_INTERVAL_S,
    format_turn_live,
    http_status_code,
)

logger = logging.getLogger(__name__)


@dataclass
class _LiveStreamState:
    openid: str
    msg_id: str
    msg_seq: int
    stream_msg_id: str = ""
    index: int = 0
    completed: bool = False


class _StreamingMixin:
    """Owns event-driven QQBot live preview state and task coordination."""

    async def _on_turn_started(self, event: TurnStarted) -> None:
        if event.channel != CHANNEL:
            return
        await self._cancel_live_tasks(event.session_key)
        self._clear_live_session(event.session_key)

    async def _on_stream_delta(self, event: StreamDeltaReady) -> None:
        if event.channel != CHANNEL or not event.content_delta:
            return
        reply = self._reply_buffers.get(event.session_key, "") + event.content_delta
        self._reply_buffers[event.session_key] = reply
        now = asyncio.get_running_loop().time()
        last_len = self._live_last_lengths.get(event.session_key, 0)
        next_at = self._live_next_at.get(event.session_key, 0.0)
        if now < next_at and len(reply) - last_len < LIVE_STREAM_MIN_CHARS:
            return
        self._live_next_at[event.session_key] = now + LIVE_STREAM_MIN_INTERVAL_S
        self._live_last_lengths[event.session_key] = len(reply)
        self._start_live_task(
            event.session_key,
            self._sync_live_message(event.session_key, event.chat_id),
        )

    async def _sync_live_message(self, session_key: str, chat_id: str) -> None:
        text = format_turn_live(self._reply_buffers.get(session_key, ""))
        if text:
            await self._send_live_stream(session_key, chat_id, text, terminal=False)

    async def _delete_live_preview(self, session_key: str) -> None:
        state = self._live_states.get(session_key)
        if state is None or not state.stream_msg_id:
            return
        try:
            await self._delete_message(state.openid, state.stream_msg_id)
        except Exception as exc:
            logger.debug("[qqbot] 临时流式消息撤回失败，忽略: %s", exc)

    async def _send_live_stream(
        self,
        session_key: str,
        chat_id: str,
        text: str,
        *,
        terminal: bool,
    ) -> bool:
        if session_key in self._live_disabled:
            return False
        kind, openid = self._parse_chat_id(chat_id)
        if kind != "c2c":
            return False
        msg_id = self._last_c2c_msg_id.get(openid)
        if not msg_id:
            return False
        lock = self._live_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            if session_key in self._live_disabled:
                return False
            state = self._live_states.setdefault(
                session_key,
                _LiveStreamState(
                    openid=openid,
                    msg_id=msg_id,
                    msg_seq=self._next_msg_seq(),
                ),
            )
            if state.completed:
                return False
            try:
                token = await self._get_access_token()
                body: dict[str, Any] = {
                    "input_mode": "replace",
                    "input_state": 10 if terminal else 1,
                    "content_type": "markdown",
                    "content_raw": text,
                    "event_id": state.msg_id,
                    "msg_id": state.msg_id,
                    "msg_seq": state.msg_seq,
                    "index": state.index,
                }
                if state.stream_msg_id:
                    body["stream_msg_id"] = state.stream_msg_id
                result = await self._api_request(
                    "POST",
                    f"/v2/users/{state.openid}/stream_messages",
                    body,
                    token,
                )
            except Exception as exc:
                failures = self._live_failures.get(session_key, 0) + 1
                self._live_failures[session_key] = failures
                status_code = http_status_code(exc)
                if (status_code is not None and status_code != 429) or (
                    failures >= LIVE_MAX_FAILURES
                ):
                    self._live_disabled.add(session_key)
                logger.warning(
                    "[qqbot] 临时流式刷新失败 session=%s failures=%d err=%s",
                    session_key,
                    failures,
                    exc,
                )
                return False
            self._live_failures[session_key] = 0
            state.stream_msg_id = str(result.get("id") or state.stream_msg_id)
            state.index += 1
            state.completed = terminal
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

    async def _cancel_live_tasks(self, session_key: str) -> None:
        tasks = list(self._live_tasks_by_session.get(session_key, set()))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _drain_live_tasks(self) -> None:
        tasks = [task for task in self._live_tasks if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _clear_live_session(self, session_key: str) -> None:
        self._live_states.pop(session_key, None)
        self._reply_buffers.pop(session_key, None)
        self._live_next_at.pop(session_key, None)
        self._live_last_lengths.pop(session_key, None)
        self._live_failures.pop(session_key, None)
        self._live_disabled.discard(session_key)
        self._live_locks.pop(session_key, None)
