"""Telegram 文本、流、文件和图片出站发送。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from telegram.constants import ChatAction
from telegram.error import Conflict, TelegramError
from telegram.ext import ContextTypes

from bus.events import OutboundMessage
from infra.channels.session_key import resolve_outbound_session_key
from infra.channels.telegram_utils import TelegramStreamMessage

from .compat import (
    _call_send_markdown,
    _call_send_stream_markdown,
    _call_send_thinking_block,
)

logger = logging.getLogger("infra.channels.telegram_channel")


class _OutboundMixin:
    """发送 Telegram 出站内容并记录投递状态。"""

    def _resolve_chat_id(self, chat_id: str) -> str:
        resolved = chat_id.lstrip("@").lower()
        if not resolved.lstrip("-").isdigit():
            resolved = self._identity_index.resolve(resolved)
            if not resolved:
                raise ValueError(
                    f"找不到用户 {chat_id!r} 的 chat_id，该用户需先给 bot 发一条消息。"
                    f"已知用户：{list(self.user_map.keys()) or '（无）'}"
                )
        return resolved

    async def send(self, chat_id: str, message: str) -> None:
        """发送文本消息（供 MessagePushTool 调用）"""
        await _call_send_markdown(
            self._app.bot,
            self._resolve_chat_id(chat_id),
            message,
            self._telegram_outbound_limiter,
        )

    async def send_stream(self, chat_id: str, message: str) -> None:
        """发送流式文本消息（私聊优先 draft，其他场景降级普通发送）"""
        await _call_send_stream_markdown(
            self._app.bot,
            self._resolve_chat_id(chat_id),
            message,
            self._telegram_outbound_limiter,
        )

    def create_stream_sender(self, chat_id: str):
        cid = int(self._resolve_chat_id(chat_id))
        if cid <= 0:
            return None
        key = str(cid)
        stream = TelegramStreamMessage(self._app.bot, cid, self._telegram_outbound_limiter)
        self._active_streams[key] = stream

        async def _push(delta: dict[str, str] | str) -> None:
            await stream.push_delta(delta)

        return _push

    async def send_file(
        self,
        chat_id: str,
        file_path: str,
        name: str | None = None,
        caption: str | None = None,
    ) -> None:
        """发送文件，可附带说明文字"""
        cid = int(self._resolve_chat_id(chat_id))
        await self._telegram_outbound_limiter.run(
            cid,
            kind="send",
            label="send_document",
            action=lambda: self._send_document_file(cid, file_path, name, caption),
        )

    async def send_image(self, chat_id: str, image: str) -> None:
        """发送图片（本地路径或 URL）"""
        cid = int(self._resolve_chat_id(chat_id))
        if image.startswith(("http://", "https://")):
            await self._telegram_outbound_limiter.run(
                cid,
                kind="send",
                label="send_photo",
                action=lambda: self._app.bot.send_photo(chat_id=cid, photo=image),
            )
        else:
            await self._telegram_outbound_limiter.run(
                cid,
                kind="send",
                label="send_photo",
                action=lambda: self._send_photo_file(cid, image),
            )

    async def _send_document_file(
        self,
        chat_id: int,
        file_path: str,
        name: str | None,
        caption: str | None,
    ) -> object:
        with open(file_path, "rb") as f:
            return await self._app.bot.send_document(
                chat_id=chat_id, document=f, filename=name, caption=caption
            )

    async def _send_photo_file(self, chat_id: int, image: str) -> object:
        with open(image, "rb") as f:
            return await self._app.bot.send_photo(chat_id=chat_id, photo=f)

    def _record_delivery_status(
        self,
        msg: OutboundMessage,
        *,
        delivery_status: str,
    ) -> None:
        if self._channel_hub is None:
            return
        self._channel_hub.mark_delivery(
            msg,
            default_channel=self._channel,
            delivery_status=delivery_status,
        )

    async def _on_response(self, msg: OutboundMessage) -> None:
        preview = msg.content[:60] + "..." if len(msg.content) > 60 else msg.content
        logger.info(f"[telegram] 发送回复  chat_id={msg.chat_id}  内容: {preview!r}")
        cid = int(self._resolve_chat_id(msg.chat_id))
        session_key = resolve_outbound_session_key(
            msg,
            default_channel=self._channel,
        )
        had_live = self._has_live_messages(session_key)
        if had_live:
            await self._cancel_live_tasks(session_key)
            await self._delete_live_message(session_key)
        final_thinking = self._final_thinking_text(session_key, msg.thinking)
        if had_live:
            if final_thinking:
                await _call_send_thinking_block(
                    self._app.bot,
                    msg.chat_id,
                    final_thinking,
                    self._telegram_outbound_limiter,
                )
            await self._send_final_tool_snapshot(session_key, msg.chat_id)
        streamed_reply = bool((msg.metadata or {}).get("streamed_reply"))
        send_failed = False
        try:
            if msg.content.strip():
                if streamed_reply:
                    stream = self._active_streams.pop(str(msg.chat_id), None)
                    if stream is not None:
                        await stream.finalize(msg.content)
                    else:
                        await _call_send_markdown(
                            self._app.bot,
                            msg.chat_id,
                            msg.content,
                            self._telegram_outbound_limiter,
                        )
                else:
                    await _call_send_markdown(
                        self._app.bot,
                        msg.chat_id,
                        msg.content,
                        self._telegram_outbound_limiter,
                    )
            if final_thinking and not had_live:
                await self._send_final_thinking(cid, msg.chat_id, final_thinking)
            self._reply_buffers.pop(session_key, None)
            self._thinking_buffers.pop(session_key, None)
            for image in (msg.media or []):
                await self.send_image(str(msg.chat_id), image)
        except Exception:
            send_failed = True
            self._record_delivery_status(msg, delivery_status="failed")
            raise
        finally:
            if not send_failed:
                self._record_delivery_status(msg, delivery_status="sent")

    async def _safe_send_typing(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> None:
        """发送 typing 状态；失败时指数退避重试，不影响消息主流程。"""
        try:
            await self._telegram_outbound_limiter.run(
                chat_id,
                kind="typing",
                label="send_chat_action",
                action=lambda: context.bot.send_chat_action(
                    chat_id=chat_id, action=ChatAction.TYPING
                ),
            )
        except Exception as e:
            logger.warning(
                "[telegram] send_chat_action 失败，已跳过 typing chat_id=%s err=%s",
                chat_id,
                e,
            )

    def _on_polling_error(self, exc: TelegramError) -> None:
        """处理 Telegram polling 异常，避免 Conflict 场景下持续刷屏。"""
        if isinstance(exc, Conflict):
            if self._polling_conflict_task is None:
                logger.error(
                    "[telegram] 检测到 getUpdates 冲突，已暂停 Telegram 接收。"
                    "请确保同一 bot token 仅运行一个轮询实例。"
                )
                self._polling_conflict_task = asyncio.create_task(
                    self._disable_polling_on_conflict()
                )
            return
        logger.warning("[telegram] polling 异常，框架将自动重试: %s", exc)

    async def _disable_polling_on_conflict(self) -> None:
        """Conflict 时关闭 updater 轮询，保留 bot 发送能力。"""
        updater = self._app.updater
        if updater is None or not updater.running:
            return
        try:
            await updater.stop()
            logger.warning(
                "[telegram] polling 已停止；当前进程不再接收 Telegram 消息。"
            )
        except Exception as e:
            logger.warning("[telegram] 停止 polling 失败: %s", e)
