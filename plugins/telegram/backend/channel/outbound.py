"""Telegram 文本、流、文件和图片出站发送。"""

from __future__ import annotations

import asyncio
import logging

from telegram.constants import ChatAction
from telegram.error import Conflict, InvalidToken, TelegramError
from telegram.ext import ContextTypes

from bus.events import OutboundMessage
from infra.channels.session_key import resolve_outbound_session_key

from ..utils import TelegramStreamMessage, sent_message_id
from ..utils.topic import telegram_topic_kwargs
from .compat import (
    _call_send_markdown,
    _call_send_stream_markdown,
    _call_send_thinking_block,
)

logger = logging.getLogger("plugins.telegram.channel")


class _OutboundMixin:
    """发送 Telegram 出站内容并记录投递状态。"""

    def _resolve_chat_id(self, chat_id: str) -> str:
        resolved = chat_id.lstrip("@").lower()
        if not resolved.lstrip("-").isdigit():
            resolved = self._require_identity_index().resolve(resolved)
            if not resolved:
                raise ValueError(
                    f"找不到用户 {chat_id!r} 的 chat_id，该用户需先给 bot 发一条消息。"
                    f"已知用户：{list(self.user_map.keys()) or '（无）'}"
                )
        return resolved

    async def send(
        self, chat_id: str, message: str, *, message_thread_id: int | None = None
    ) -> str | None:
        """发送文本消息（供 MessagePushTool 调用），返回首条消息 id。"""
        return await _call_send_markdown(
            self._app.bot,
            self._resolve_chat_id(chat_id),
            message,
            self._telegram_outbound_limiter,
            **({"message_thread_id": message_thread_id} if message_thread_id else {}),
        )

    async def send_stream(self, chat_id: str, message: str) -> str | None:
        """发送流式文本消息（私聊优先 draft，其他场景降级普通发送），返回消息 id。"""
        return await _call_send_stream_markdown(
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
        stream = TelegramStreamMessage(
            self._app.bot, cid, self._telegram_outbound_limiter
        )
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
        *,
        message_thread_id: int | None = None,
    ) -> str | None:
        """发送文件，可附带说明文字；返回消息 id。"""
        cid = int(self._resolve_chat_id(chat_id))
        sent = await self._telegram_outbound_limiter.run(
            cid,
            kind="send",
            label="send_document",
            action=lambda: self._send_document_file(
                cid, file_path, name, caption, message_thread_id
            ),
        )
        return sent_message_id(sent)

    async def send_image(
        self, chat_id: str, image: str, *, message_thread_id: int | None = None
    ) -> str | None:
        """发送图片（本地路径或 URL），返回消息 id。"""
        cid = int(self._resolve_chat_id(chat_id))
        if image.startswith(("http://", "https://")):
            sent = await self._telegram_outbound_limiter.run(
                cid,
                kind="send",
                label="send_photo",
                action=lambda: self._app.bot.send_photo(
                    chat_id=cid,
                    photo=image,
                    **telegram_topic_kwargs(message_thread_id),
                ),
            )
        else:
            sent = await self._telegram_outbound_limiter.run(
                cid,
                kind="send",
                label="send_photo",
                action=lambda: self._send_photo_file(cid, image, message_thread_id),
            )
        return sent_message_id(sent)

    async def _send_document_file(
        self,
        chat_id: int,
        file_path: str,
        name: str | None,
        caption: str | None,
        message_thread_id: int | None,
    ) -> object:
        with open(file_path, "rb") as f:
            return await self._app.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=name,
                caption=caption,
                **telegram_topic_kwargs(message_thread_id),
            )

    async def _send_photo_file(
        self, chat_id: int, image: str, message_thread_id: int | None
    ) -> object:
        with open(image, "rb") as f:
            return await self._app.bot.send_photo(
                chat_id=chat_id,
                photo=f,
                **telegram_topic_kwargs(message_thread_id),
            )

    def _record_delivery_status(
        self,
        msg: OutboundMessage,
        *,
        delivery_status: str,
        external_message_id: str | None = None,
    ) -> None:
        if self._channel_hub is None:
            return
        self._channel_hub.mark_delivery(
            msg,
            default_channel=self._channel,
            delivery_status=delivery_status,
            external_message_id=external_message_id or "",
        )

    async def _on_response(self, msg: OutboundMessage) -> None:
        preview = msg.content[:60] + "..." if len(msg.content) > 60 else msg.content
        logger.info(f"[telegram] 发送回复  chat_id={msg.chat_id}  内容: {preview!r}")
        cid = int(self._resolve_chat_id(msg.chat_id))
        topic = (msg.metadata or {}).get("message_thread_id")
        message_thread_id = topic if isinstance(topic, int) and topic > 0 else None
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
                    **(
                        {"message_thread_id": message_thread_id}
                        if message_thread_id
                        else {}
                    ),
                )
            await self._send_final_tool_snapshot(session_key, msg.chat_id)
        streamed_reply = bool((msg.metadata or {}).get("streamed_reply"))
        first_id: str | None = None
        receipts: list[str] = []
        stream = None
        try:
            if msg.content.strip():
                if streamed_reply:
                    stream = self._active_streams.pop(str(msg.chat_id), None)
                if stream is not None:
                    await stream.finalize(msg.content)
                    first_id = stream.message_id
                else:
                    first_id = await _call_send_markdown(
                        self._app.bot,
                        msg.chat_id,
                        msg.content,
                        self._telegram_outbound_limiter,
                        on_receipt=receipts.append,
                        **(
                            {"message_thread_id": message_thread_id}
                            if message_thread_id
                            else {}
                        ),
                    )
            if final_thinking and not had_live:
                await self._send_final_thinking(
                    cid, msg.chat_id, final_thinking, message_thread_id
                )
            self._reply_buffers.pop(session_key, None)
            self._thinking_buffers.pop(session_key, None)
            for image in msg.media or []:
                image_id = await self.send_image(
                    str(msg.chat_id), image, message_thread_id=message_thread_id
                )
                first_id = first_id or image_id
        except BaseException:
            # A later chunk/edit can fail after an earlier message was accepted.
            first_id = first_id or (stream.message_id if stream is not None else None)
            first_id = first_id or next(iter(receipts), None)
            self._record_delivery_status(
                msg, delivery_status="failed", external_message_id=first_id
            )
            raise
        else:
            self._record_delivery_status(
                msg, delivery_status="sent", external_message_id=first_id
            )

    async def _safe_send_typing(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_thread_id: int | None = None,
    ) -> None:
        """发送 typing 状态；失败时指数退避重试，不影响消息主流程。"""
        try:
            await self._telegram_outbound_limiter.run(
                chat_id,
                kind="typing",
                label="send_chat_action",
                action=lambda: context.bot.send_chat_action(
                    chat_id=chat_id,
                    action=ChatAction.TYPING,
                    **telegram_topic_kwargs(message_thread_id),
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
            self._online = False
            self._report_account("error", "Telegram getUpdates conflict")
            if self._polling_conflict_task is None:
                logger.error(
                    "[telegram] 检测到 getUpdates 冲突，已暂停 Telegram 接收。"
                    "请确保同一 bot token 仅运行一个轮询实例。"
                )
                self._polling_conflict_task = asyncio.create_task(
                    self._disable_polling_on_conflict()
                )
            return
        if isinstance(exc, InvalidToken):
            self._online = False
            self._report_account("login_required", "Invalid Bot Token")
            return
        self._online = False
        self._report_account("connecting", str(exc).replace(self._token, "[redacted]"))
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
