"""Telegram 图片与文档入站处理。"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .formatting import _build_inbound_text_with_reply

logger = logging.getLogger("infra.channels.telegram_channel")


class _MediaMixin:
    """下载并发布 Telegram 图片和文档消息。"""

    async def _on_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        user = update.effective_user

        if not msg or not msg.photo or not chat or not user:
            return

        if not self._is_allowed(user):
            logger.warning(
                f"[telegram] 拒绝未授权用户  id={user.id}  username=@{user.username}"
            )
            return

        msg_key = f"{chat.id}:{msg.message_id}"
        if self._message_deduper.seen(msg_key):
            logger.warning(
                f"[telegram] 重复图片消息已忽略  chat_id={chat.id}  message_id={msg.message_id}"
            )
            return

        chat_id_str = str(chat.id)
        await self._remember_username(chat_id_str, user.username)

        await self._safe_send_typing(context, chat.id)

        # 下载最高分辨率的图片到持久化目录
        tg_file = await context.bot.get_file(msg.photo[-1].file_id)
        tmp = self._attachments.create_path("photo_", ".jpg")
        await tg_file.download_to_drive(tmp)
        logger.info(
            f"[telegram] 收到图片  chat_id={chat.id}  user=@{user.username or user.id}  path={tmp}"
        )
        caption_text = msg.caption or ""
        inbound_text, reply_meta = _build_inbound_text_with_reply(
            caption_text, msg.reply_to_message
        )
        media = [str(tmp)]
        if msg.reply_to_message and getattr(msg.reply_to_message, "photo", None):
            try:
                reply_file = await context.bot.get_file(
                    msg.reply_to_message.photo[-1].file_id
                )
                reply_tmp = self._attachments.create_path("reply_photo_", ".jpg")
                await reply_file.download_to_drive(reply_tmp)
                media.append(str(reply_tmp))
                logger.info(
                    f"[telegram] 下载被回复图片  chat_id={chat.id}  tmp={reply_tmp}"
                )
            except Exception as e:
                logger.warning(
                    f"[telegram] 被回复图片下载失败  chat_id={chat.id}  err={e}"
                )
        await self._publish_telegram_inbound(
            sender=str(user.id),
            chat_id=str(chat.id),
            content=inbound_text,
            media=media,
            metadata={
                "username": user.username or "",
                "chat_type": str(getattr(chat, "type", "private") or "private"),
                **reply_meta,
            },
        )

    async def _on_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        chat = update.effective_chat
        user = update.effective_user

        if not msg or not msg.document or not chat or not user:
            return

        if not self._is_allowed(user):
            logger.warning(
                f"[telegram] 拒绝未授权用户  id={user.id}  username=@{user.username}"
            )
            return

        chat_id_str = str(chat.id)
        await self._remember_username(chat_id_str, user.username)

        await self._safe_send_typing(context, chat.id)

        doc = msg.document
        suffix = ""
        if doc.file_name and "." in doc.file_name:
            suffix = "." + doc.file_name.rsplit(".", 1)[-1]
        tg_file = await context.bot.get_file(doc.file_id)
        tmp = self._attachments.create_path("doc_", suffix)
        await tg_file.download_to_drive(tmp)
        logger.info(
            f"[telegram] 收到文件  chat_id={chat.id}  user=@{user.username or user.id}"
            f"  filename={doc.file_name!r}  tmp={tmp}"
        )

        caption_text = msg.caption or ""
        inbound_text, reply_meta = _build_inbound_text_with_reply(
            caption_text, msg.reply_to_message
        )
        if doc.file_name:
            inbound_text = f"[文件: {doc.file_name}]\n{inbound_text}".strip()
        await self._publish_telegram_inbound(
            sender=str(user.id),
            chat_id=str(chat.id),
            content=inbound_text,
            media=[str(tmp)],
            metadata={
                "username": user.username or "",
                "chat_type": str(getattr(chat, "type", "private") or "private"),
                "document_filename": doc.file_name or "",
                "document_mime_type": doc.mime_type or "",
                **reply_meta,
            },
        )
