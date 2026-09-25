"""Telegram 命令处理。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .compat import _call_send_markdown

logger = logging.getLogger("plugins.telegram.channel")


class _CommandMixin:
    """处理 stop 与通用 Telegram 命令。"""

    async def _on_stop_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        user = update.effective_user

        if not msg or not chat or not user:
            return
        # /stop follows the same admission as messages: bound and not blacklisted.
        if self._channel_hub is not None and not self._channel_hub.is_sender_allowed(
            channel=self._channel,
            chat_id=str(chat.id),
            sender_id=str(user.id),
            sender_alias=user.username or "",
        ):
            logger.warning(
                f"[telegram] 忽略未绑定渠道或黑名单成员的 /stop  chat_id={chat.id}  id={user.id}"
            )
            return
        if self._interrupt_controller is None:
            await _call_send_markdown(
                self._app.bot,
                str(chat.id),
                "当前未启用中断功能。",
                self._telegram_outbound_limiter,
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
            sender=str(user.id),
            command="/stop",
        )
        await _call_send_markdown(
            self._app.bot,
            str(chat.id),
            result.message,
            self._telegram_outbound_limiter,
        )

    async def _on_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        user = update.effective_user

        if not msg or not chat or not user:
            return
        await self._publish_telegram_inbound(
            sender=str(user.id),
            chat_id=str(chat.id),
            content=str(getattr(msg, "text", "") or ""),
            metadata={
                "username": user.username or "",
                "chat_type": str(getattr(chat, "type", "private") or "private"),
            },
        )
