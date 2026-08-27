"""Telegram 推理流与工具调用 live 状态。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from bus.events_lifecycle import (
    StreamDeltaReady,
    ToolCallCompleted,
    ToolCallStarted,
    TurnStarted,
)
from infra.channels.telegram_utils import TelegramLiveTextMessage

from .compat import _call_send_markdown, _call_send_thinking_block
from .formatting import (
    _LIVE_STREAM_MIN_CHARS,
    _LIVE_STREAM_MIN_INTERVAL_S,
    _TOOL_LIVE_TAIL,
    _ToolLiveLine,
    _format_tool_intent,
    _format_tool_live,
    _format_tool_target,
    _format_turn_live,
    _live_buffer_len,
    _tail_text,
)

logger = logging.getLogger("infra.channels.telegram_channel")


class _StreamingMixin:
    """维护 Telegram live 消息、流式回复和工具快照。"""

    def _start_live_task(
        self,
        session_key: str,
        coro: Coroutine[Any, Any, None],
    ) -> None:
        task = asyncio.create_task(coro)
        self._live_tasks.add(task)
        self._live_tasks_by_session.setdefault(session_key, set()).add(task)

        def _done(done_task: asyncio.Task[None]) -> None:
            self._live_tasks.discard(done_task)
            for tasks in self._live_tasks_by_session.values():
                tasks.discard(done_task)
            try:
                _ = done_task.result()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[telegram] live 更新任务失败: %s", e)

        task.add_done_callback(_done)

    async def _cancel_live_tasks(self, session_key: str) -> None:
        tasks = [task for task in self._live_tasks_by_session.get(session_key, set()) if not task.done()]
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _on_turn_started(self, event: TurnStarted) -> None:
        if event.channel != self._channel:
            return
        await self._cancel_live_tasks(event.session_key)
        _ = self._tool_lines.pop(event.session_key, None)
        _ = self._reply_buffers.pop(event.session_key, None)
        _ = self._thinking_buffers.pop(event.session_key, None)
        _ = self._thinking_live_next_at.pop(event.session_key, None)
        _ = self._live_last_lengths.pop(event.session_key, None)
        _ = self._live_messages.pop(event.session_key, None)

    async def _on_stream_delta(self, event: StreamDeltaReady) -> None:
        if event.channel != self._channel:
            return
        if not event.content_delta and not event.thinking_delta:
            return
        cid = int(self._resolve_chat_id(event.chat_id))
        if cid <= 0:
            return
        if event.content_delta:
            reply = self._reply_buffers.get(event.session_key, "")
            self._reply_buffers[event.session_key] = reply + event.content_delta
        if event.thinking_delta:
            thinking = self._thinking_buffers.get(event.session_key, "")
            self._thinking_buffers[event.session_key] = thinking + event.thinking_delta
        live_len = _live_buffer_len(
            self._reply_buffers.get(event.session_key, ""),
            self._thinking_buffers.get(event.session_key, ""),
        )
        last_len = self._live_last_lengths.get(event.session_key, 0)
        now = asyncio.get_running_loop().time()
        next_at = self._thinking_live_next_at.get(event.session_key, 0.0)
        if now < next_at and live_len - last_len < _LIVE_STREAM_MIN_CHARS:
            return
        self._thinking_live_next_at[event.session_key] = now + _LIVE_STREAM_MIN_INTERVAL_S
        self._live_last_lengths[event.session_key] = live_len
        self._start_live_task(
            event.session_key,
            self._sync_live_message(event.session_key, cid),
        )

    async def _on_tool_call_started(self, event: ToolCallStarted) -> None:
        if event.channel != self._channel:
            return
        cid = int(self._resolve_chat_id(event.chat_id))
        if cid <= 0:
            return
        lines = self._tool_lines.setdefault(event.session_key, [])
        lines.append(
            _ToolLiveLine(
                call_id=event.call_id,
                tool_name=event.tool_name,
                intent=_format_tool_intent(event.arguments),
                target=_format_tool_target(event.arguments),
            )
        )
        self._start_live_task(
            event.session_key,
            self._sync_live_message(event.session_key, cid),
        )

    async def _on_tool_call_completed(self, event: ToolCallCompleted) -> None:
        if event.channel != self._channel:
            return
        cid = int(self._resolve_chat_id(event.chat_id))
        if cid <= 0:
            return
        lines = self._tool_lines.setdefault(event.session_key, [])
        line = next((item for item in lines if item.call_id == event.call_id), None)
        if line is None:
            line = _ToolLiveLine(
                call_id=event.call_id,
                tool_name=event.tool_name,
                intent=_format_tool_intent(event.final_arguments or event.arguments),
                target=_format_tool_target(event.final_arguments or event.arguments),
            )
            lines.append(line)
        line.status = "error" if event.status == "error" else "done"
        self._start_live_task(
            event.session_key,
            self._sync_live_message(event.session_key, cid),
        )

    async def _sync_live_message(
        self,
        session_key: str,
        chat_id: int,
        *,
        terminal: bool = False,
    ) -> None:
        text, html_text = _format_turn_live(
            self._tool_lines.get(session_key, []),
            self._reply_buffers.get(session_key, ""),
            self._thinking_buffers.get(session_key, ""),
            terminal=terminal,
        )
        if not text:
            return
        message = self._live_messages.get(session_key)
        if message is None:
            message = TelegramLiveTextMessage(
                self._app.bot,
                self._live_edit_queue,
                chat_id,
            )
            self._live_messages[session_key] = message
        await message.update(text, html_text=html_text, force=terminal)

    def _has_live_messages(self, session_key: str) -> bool:
        return session_key in self._live_messages

    async def _delete_live_message(self, session_key: str) -> None:
        message = self._live_messages.pop(session_key, None)
        if message is not None:
            await message.delete()

    async def _drain_live_tasks(self) -> None:
        tasks = [task for task in self._live_tasks if not task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _final_thinking_text(
        self,
        session_key: str,
        thinking: str | None,
    ) -> str:
        streamed = self._thinking_buffers.get(session_key, "").strip()
        final = (thinking or "").strip()
        if streamed and final:
            if final in streamed:
                return streamed
            if streamed in final:
                return final
            return f"{streamed}\n\n{final}"
        return streamed or final

    async def _send_final_thinking(
        self,
        chat_id: int,
        original_chat_id: str,
        thinking: str,
    ) -> None:
        if not thinking:
            return
        await _call_send_thinking_block(
            self._app.bot,
            original_chat_id,
            thinking,
            self._telegram_outbound_limiter,
        )

    async def _send_final_tool_snapshot(
        self,
        session_key: str,
        chat_id: str,
    ) -> None:
        lines = self._tool_lines.get(session_key, [])
        if not lines:
            return
        tool_text = _tail_text(_format_tool_live(lines), _TOOL_LIVE_TAIL)
        if tool_text:
            await _call_send_markdown(
                self._app.bot,
                chat_id,
                f"```\n{tool_text}\n```",
                self._telegram_outbound_limiter,
            )
