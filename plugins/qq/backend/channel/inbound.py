from __future__ import annotations

import logging

from bus.events import InboundMessage
from core.common.channel_identifiers import normalize_qq_group_chat_id

from .compat import download_to_temp
from .formatting import CHANNEL

logger = logging.getLogger(__name__)


class _InboundMixin:
    """Owns QQ private/group normalization, authorization, and stop routing."""

    async def _handle_private(
        self, user_id: str, content: str, img_urls: list[str] | None = None
    ) -> None:
        await self._require_identity_index().remember(user_id, user_id)
        media = await download_to_temp(
            img_urls or [], self._require_http_requester(), self._attachments
        )
        await self._publish_inbound(
            InboundMessage(
                channel=CHANNEL,
                sender=user_id,
                chat_id=user_id,
                content=content,
                media=media,
                metadata={"chat_type": "private"},
            )
        )

    async def _handle_stop_private(self, user_id: str) -> None:
        if not self._is_stop_admitted(user_id, user_id):
            return
        if self._interrupt_controller is None:
            await self.send(user_id, "当前未启用中断功能。")
            return
        result = self._interrupt_controller.request_interrupt(
            session_key=self._resolve_runtime_session_key(user_id),
            sender=user_id,
            command="/stop",
        )
        await self.send(user_id, result.message)

    async def _handle_group(
        self,
        group_id: str,
        user_id: str,
        content: str,
        img_urls: list[str] | None = None,
    ) -> None:
        chat_id = normalize_qq_group_chat_id(group_id)
        sessions = self._require_session_manager()
        session = sessions.get_or_create(f"{CHANNEL}:{chat_id}")
        if "group_id" not in session.metadata:
            session.metadata["group_id"] = group_id
            await sessions.save_async(session)
        media = await download_to_temp(
            img_urls or [], self._require_http_requester(), self._attachments
        )
        await self._publish_inbound(
            InboundMessage(
                channel=CHANNEL,
                sender=user_id,
                chat_id=chat_id,
                content=content,
                media=media,
                metadata={
                    "chat_type": "group",
                    "group_id": group_id,
                    "sender_id": user_id,
                },
            )
        )

    async def _publish_inbound(self, message: InboundMessage) -> None:
        await self._intake.submit(message)

    async def _accept_inbound(self, message: InboundMessage) -> None:
        if self._channel_hub is not None:
            if not self._channel_hub.is_sender_allowed(
                channel=message.channel,
                chat_id=message.chat_id,
                sender_id=message.sender,
            ):
                logger.warning(
                    "[qq] 忽略未绑定渠道或黑名单成员的消息 chat_id=%s", message.chat_id
                )
                return
            message = self._channel_hub.route_inbound(message)
        if message.metadata.get("conversation_duplicate"):
            return
        await self._require_bus().publish_inbound(message)

    async def _handle_stop_group(self, group_id: str, user_id: str) -> None:
        chat_id = normalize_qq_group_chat_id(group_id)
        if not self._is_stop_admitted(chat_id, user_id):
            return
        if self._interrupt_controller is None:
            await self.send(chat_id, "当前未启用中断功能。")
            return
        result = self._interrupt_controller.request_interrupt(
            session_key=self._resolve_runtime_session_key(chat_id),
            sender=user_id,
            command="/stop",
        )
        await self.send(chat_id, result.message)

    def _is_stop_admitted(self, chat_id: str, user_id: str) -> bool:
        """``/stop`` follows the same admission as messages: bound and not blacklisted."""
        if self._channel_hub is None or self._channel_hub.is_sender_allowed(
            channel=CHANNEL, chat_id=chat_id, sender_id=user_id
        ):
            return True
        logger.warning("[qq] 忽略未绑定渠道或黑名单成员的 /stop chat_id=%s", chat_id)
        return False

    def _resolve_runtime_session_key(self, chat_id: str) -> str:
        if self._channel_hub is not None:
            return self._channel_hub.resolve_runtime_session_key(CHANNEL, chat_id)
        return f"{CHANNEL}:{chat_id}"
