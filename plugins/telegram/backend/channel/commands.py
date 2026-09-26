"""Telegram 命令处理。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from core.channels.chat_id_command import answer_chat_id_command

from ..utils.topic import telegram_topic_kwargs
from .compat import _call_send_markdown
from .identity import message_subject, message_topic_metadata

logger = logging.getLogger("plugins.telegram.channel")


class _CommandMixin:
    """处理 stop 与通用 Telegram 命令。"""

    async def _on_stop_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        user, sender_id, _ = (
            message_subject(msg, update.effective_user) if msg else (None, "", "user")
        )

        if not msg or not chat or not user:
            return
        self._remember_chat(chat, user, msg)
        # /stop follows the same admission as messages: bound and not blacklisted.
        if not self._is_sender_admitted(chat, user, "/stop", sender_id=sender_id):
            return
        if self._interrupt_controller is None:
            await _call_send_markdown(
                self._app.bot,
                str(chat.id),
                "当前未启用中断功能。",
                self._telegram_outbound_limiter,
                **telegram_topic_kwargs(getattr(msg, "message_thread_id", None)),
            )
            return

        session_key = (
            self._channel_hub.resolve_runtime_session_key(
                self._channel,
                str(chat.id),
            )
            if self._channel_hub is not None
            else f"{self._channel}:{chat.id}"
        )
        result = self._interrupt_controller.request_interrupt(
            session_key=session_key,
            sender=sender_id,
            command="/stop",
        )
        await _call_send_markdown(
            self._app.bot,
            str(chat.id),
            result.message,
            self._telegram_outbound_limiter,
            **telegram_topic_kwargs(getattr(msg, "message_thread_id", None)),
        )

    async def _on_chat_id_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Answers ``/chatid``; the admission exception is documented there."""
        msg = update.effective_message
        chat = update.effective_chat
        user, sender_id, _ = (
            message_subject(msg, update.effective_user) if msg else (None, "", "user")
        )
        if not chat or not user:
            return
        if msg:
            self._remember_chat(chat, user, msg)
        chat_id = str(chat.id)
        await answer_chat_id_command(
            self._channel_hub,
            channel=self._channel,
            chat_id=chat_id,
            chat_type="private" if chat.type == "private" else "group",
            sender_id=sender_id,
            sender_alias=user.username or "",
            declarations=self._chat_types,
            send=lambda text: _call_send_markdown(
                self._app.bot,
                chat_id,
                text,
                self._telegram_outbound_limiter,
                **telegram_topic_kwargs(getattr(msg, "message_thread_id", None)),
            ),
        )

    async def _on_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        user, sender_id, sender_kind = (
            message_subject(msg, update.effective_user) if msg else (None, "", "user")
        )

        if not msg or not chat or not user:
            return
        self._remember_chat(chat, user, msg)
        if not self._is_sender_admitted(chat, user, "命令", sender_id=sender_id):
            return
        await self._publish_telegram_inbound(
            sender=sender_id,
            chat_id=str(chat.id),
            content=str(getattr(msg, "text", "") or ""),
            metadata={
                "username": user.username or "",
                "sender_kind": sender_kind,
                "chat_type": str(getattr(chat, "type", "private") or "private"),
                "chat_title": str(getattr(chat, "title", "") or ""),
                "external_message_id": str(msg.message_id),
                **message_topic_metadata(msg),
            },
        )
