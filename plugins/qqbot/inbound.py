from __future__ import annotations

import logging
from typing import Any

from bus.events import InboundMessage

from .formatting import CHANNEL, as_dict

logger = logging.getLogger(__name__)


class _InboundMixin:
    """Normalizes QQBot Gateway events and publishes role-routed C2C messages."""

    async def _handle_dispatch(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type == "C2C_MESSAGE_CREATE":
            await self._handle_c2c(data)
        elif event_type.startswith("GROUP_"):
            logger.debug("[qqbot] 当前仅启用私聊模式，忽略群事件 event=%s", event_type)

    async def _handle_c2c(self, data: dict[str, Any]) -> None:
        author = as_dict(data.get("author"))
        user_openid = str(
            author.get("user_openid") or data.get("user_openid") or ""
        ).strip()
        if not user_openid:
            return
        if self._allow_from and user_openid not in self._allow_from:
            logger.warning("[qqbot] 拒绝未授权私聊用户 user_openid=%s", user_openid)
            return
        content = str(data.get("content") or "").strip()
        message_id = str(data.get("id") or "").strip()
        if message_id:
            self._last_c2c_msg_id[user_openid] = message_id
            await self._send_input_notify(user_openid, message_id)
        chat_id = f"c2c:{user_openid}"
        logger.info(
            "[qqbot] 收到私聊消息 user_openid=%s msg_id=%s",
            user_openid,
            message_id,
        )
        if content == "/stop":
            await self._handle_stop(chat_id, user_openid)
            return
        await self._publish_inbound(
            InboundMessage(
                channel=CHANNEL,
                sender=user_openid,
                chat_id=chat_id,
                content=content,
                metadata={
                    "chat_type": "private",
                    "user_openid": user_openid,
                    "message_id": message_id,
                    "external_message_id": message_id,
                },
            )
        )

    async def _publish_inbound(self, message: InboundMessage) -> None:
        if self._channel_hub is not None:
            if not self._channel_hub.is_sender_allowed(
                channel=message.channel,
                chat_id=message.chat_id,
                sender_id=message.sender,
            ):
                logger.warning(
                    "[qqbot] 拒绝未绑定渠道或未授权用户 chat_id=%s",
                    message.chat_id,
                )
                return
            message = self._channel_hub.route_inbound(message)
        if message.metadata.get("conversation_duplicate"):
            return
        await self._require_bus().publish_inbound(message)

    async def _handle_stop(self, chat_id: str, sender: str) -> None:
        if self._interrupt_controller is None:
            await self.send(chat_id, "当前未启用中断功能。")
            return
        session_key = (
            self._channel_hub.resolve_runtime_session_key(CHANNEL, chat_id)
            if self._channel_hub is not None
            else f"{CHANNEL}:{chat_id}"
        )
        result = self._interrupt_controller.request_interrupt(
            session_key=session_key,
            sender=sender,
            command="/stop",
        )
        await self.send(chat_id, result.message)
