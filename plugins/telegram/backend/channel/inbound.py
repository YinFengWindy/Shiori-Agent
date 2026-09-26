"""Telegram 普通消息的入站解析与发布。"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from bus.events import InboundMessage

from .formatting import _build_inbound_text_with_reply
from .identity import message_mentioned_bot, message_subject, message_topic_metadata

logger = logging.getLogger("plugins.telegram.channel")


class _InboundMixin:
    """处理文本消息并发布标准入站事件。"""

    async def _on_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        user, sender_id, sender_kind = (
            message_subject(msg, update.effective_user) if msg else (None, "", "user")
        )

        if not msg or not msg.text or not chat or not user:
            return
        self._remember_chat(chat, user, msg)
        if not self._is_sender_admitted(chat, user, "消息", sender_id=sender_id):
            return

        # 去重：同一 (chat_id, message_id) 只处理一次，防止 Telegram 重投
        msg_key = f"{chat.id}:{msg.message_id}"
        if self._message_deduper.seen(msg_key):
            logger.warning(
                f"[telegram] 重复消息已忽略  chat_id={chat.id}  message_id={msg.message_id}"
            )
            return

        preview = msg.text[:60] + "..." if len(msg.text) > 60 else msg.text
        logger.info(
            f"[telegram] 收到消息  chat_id={chat.id}  "
            f"user=@{user.username or user.id}  内容: {preview!r}"
        )
        # 更新内存索引 + 持久化到 session.metadata
        chat_id_str = str(chat.id)
        await self._remember_username(chat_id_str, user.username)

        await self._safe_send_typing(
            context, chat.id, getattr(msg, "message_thread_id", None)
        )

        inbound_text, reply_meta = _build_inbound_text_with_reply(
            msg.text, msg.reply_to_message
        )
        reply_media: list[str] = []
        if msg.reply_to_message and getattr(msg.reply_to_message, "photo", None):
            try:
                tg_file = await context.bot.get_file(
                    msg.reply_to_message.photo[-1].file_id
                )
                tmp = self._attachments.create_path("reply_photo_", ".jpg")
                await tg_file.download_to_drive(tmp)
                reply_media.append(str(tmp))
                logger.info(f"[telegram] 下载被回复图片  chat_id={chat.id}  tmp={tmp}")
            except Exception as e:
                logger.warning(
                    f"[telegram] 被回复图片下载失败  chat_id={chat.id}  err={e}"
                )
        if msg.reply_to_message and getattr(msg.reply_to_message, "document", None):
            try:
                rdoc = msg.reply_to_message.document
                if rdoc is None:
                    raise ValueError("reply document 缺失")
                suffix = ""
                if rdoc.file_name and "." in rdoc.file_name:
                    suffix = "." + rdoc.file_name.rsplit(".", 1)[-1]
                tg_file = await context.bot.get_file(rdoc.file_id)
                tmp = self._attachments.create_path("reply_doc_", suffix)
                await tg_file.download_to_drive(tmp)
                reply_media.append(str(tmp))
                logger.info(
                    f"[telegram] 下载被回复文件  chat_id={chat.id}  filename={rdoc.file_name!r}  tmp={tmp}"
                )
            except Exception as e:
                logger.warning(
                    f"[telegram] 被回复文件下载失败  chat_id={chat.id}  err={e}"
                )
        await self._publish_inbound(
            InboundMessage(
                channel=self._channel,
                sender=sender_id,
                chat_id=str(chat.id),
                content=inbound_text,
                media=reply_media,
                metadata={
                    "account_id": getattr(self, "_account_id", None) or "",
                    "mentioned": message_mentioned_bot(
                        msg, getattr(self, "_bot_username", "")
                    ),
                    "username": user.username or "",
                    "sender_kind": sender_kind,
                    "chat_type": str(getattr(chat, "type", "private") or "private"),
                    "external_message_id": str(msg.message_id),
                    "chat_title": str(getattr(chat, "title", "") or ""),
                    **message_topic_metadata(msg),
                    **reply_meta,
                },
            )
        )

    def _is_sender_admitted(
        self, chat: Any, user: Any, kind: str, *, sender_id: str | None = None
    ) -> bool:
        """Checks the role binding's admission before any side effect of an update.

        Rejected updates (unbound chat, blacklisted member) only record that a
        conversation was observed; they must not show typing, remember member
        usernames or download attachments. ``_accept_inbound``
        repeats the check because paused intake may replay a message after the
        bindings changed. ``kind`` names what was rejected (``消息``, ``/stop``)
        for the warning log.
        """
        if self._channel_hub is None or self._channel_hub.is_sender_allowed(
            channel=self._channel,
            chat_id=str(chat.id),
            sender_id=sender_id or str(user.id),
            sender_alias=user.username or "",
            account_id=self._account_id or "",
        ):
            return True
        logger.warning(
            "[telegram] 忽略未绑定渠道或黑名单成员的 %s  chat_id=%s  id=%s",
            kind,
            chat.id,
            sender_id or user.id,
        )
        return False

    def _route_inbound(self, message: InboundMessage) -> InboundMessage | None:
        if self._channel_hub is None:
            return message
        if "account_id" in message.metadata and callable(
            getattr(self._channel_hub, "route_account_inbound", None)
        ):
            return self._channel_hub.route_account_inbound(message)
        return self._channel_hub.route_inbound(message)

    async def _publish_inbound(self, message: InboundMessage) -> None:
        await self._intake.submit(message)

    async def _accept_inbound(self, message: InboundMessage) -> None:
        self.mark_online()
        if self._channel_hub is not None and not self._channel_hub.is_sender_allowed(
            channel=message.channel,
            chat_id=message.chat_id,
            sender_id=message.sender,
            sender_alias=str(message.metadata.get("username") or ""),
            account_id=str(message.metadata.get("account_id") or ""),
        ):
            logger.warning(
                "[telegram] 忽略未绑定渠道或黑名单成员的消息 chat_id=%s",
                message.chat_id,
            )
            return
        routed = self._route_inbound(message)
        if routed is None or routed.metadata.get("conversation_duplicate"):
            return
        await self._require_bus().publish_inbound(routed)

    async def _publish_telegram_inbound(
        self,
        *,
        sender: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        await self._publish_inbound(
            InboundMessage(
                channel=self._channel,
                sender=sender,
                chat_id=chat_id,
                content=content,
                media=list(media or []),
                metadata={
                    "account_id": getattr(self, "_account_id", None) or "",
                    **dict(metadata or {}),
                },
            )
        )
