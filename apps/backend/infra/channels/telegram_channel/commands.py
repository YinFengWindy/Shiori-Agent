"""Telegram 命令处理。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .compat import _call_send_markdown

logger = logging.getLogger("infra.channels.telegram_channel")


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
        if not self._is_allowed(user):
            logger.warning(
                f"[telegram] 拒绝未授权 /stop  id={user.id}  username=@{user.username}"
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
        if not self._is_allowed(user):
            logger.warning(
                f"[telegram] 拒绝未授权命令  id={user.id}  username=@{user.username}"
            )
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
