"""Route public QQBot channel traffic to its owning application gateway."""

from __future__ import annotations

from typing import Any

from .channel import QQBotChannel
from .formatting import CHANNEL, SYSTEM_PROMPT_HINT


class _AccountDispatchMixin:
    """Requires the composite channel's application-ID keyed `_channels`."""

    _channels: dict[str, QQBotChannel]

    def _for_chat(self, chat_id: str) -> QQBotChannel:
        kind, target = QQBotChannel._split_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("QQBot 当前仅支持 C2C 私聊")
        app_id = target.split(":", 1)[0]
        channel = self._channels.get(app_id)
        if channel is not None and channel._scoped:
            return channel
        if ":" in target:
            raise RuntimeError("QQBot 目标所属应用账号未连接")
        legacy = [item for item in self._channels.values() if not item._scoped]
        if len(legacy) == 1:
            return legacy[0]
        raise ValueError("QQBot 目标缺少有效应用账号作用域")

    async def send(self, chat_id: str, message: str) -> str | None:
        """Route a host C2C send to its application gateway."""
        return await self._for_chat(chat_id).send(chat_id, message)

    async def send_proactive(self, chat_id: str, message: str) -> str | None:
        """Send proactive text through the application named by chat ID."""
        return await self.send(chat_id, message)

    async def send_image(self, chat_id: str, image: str) -> str | None:
        """Send an image without crossing application target scopes."""
        return await self._for_chat(chat_id).send_image(chat_id, image)

    async def send_stream(self, chat_id: str, message: str) -> str | None:
        """Send a completed stream through its owning application."""
        return await self._for_chat(chat_id).send_stream(chat_id, message)

    def supports_stream_events(self, chat_id: str) -> bool:
        """Report live preview support only for connected C2C targets."""
        try:
            return self._for_chat(chat_id).supports_stream_events(chat_id)
        except (RuntimeError, ValueError):
            return False

    def system_prompt_hint(self, chat_id: str) -> str:
        """Keep official QQBot targets distinct from NapCat QQ targets."""
        return SYSTEM_PROMPT_HINT

    async def _on_response(self, message: Any) -> None:
        await self._for_chat(message.chat_id)._on_response(message)

    async def _on_turn_started(self, event: Any) -> None:
        if event.channel == CHANNEL:
            await self._for_chat(event.chat_id)._on_turn_started(event)

    async def _on_stream_delta(self, event: Any) -> None:
        if event.channel == CHANNEL:
            await self._for_chat(event.chat_id)._on_stream_delta(event)

    async def _on_turn_cancelled(self, event: Any) -> None:
        if event.channel == CHANNEL:
            await self._for_chat(event.chat_id)._on_turn_cancelled(event)
