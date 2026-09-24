"""Turns ``im.message.receive_v1`` events into text, media and reply context."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from core.common.media import detect_image_mime_from_header
from infra.channels.base import AttachmentStore
from infra.channels.reply_context import build_inbound_text_with_reply_context

from .api import FeishuApi
from .formatting import (
    as_dict,
    as_list,
    extract_card_text,
    extract_post,
    extract_text,
    load_json_object,
)

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class ReceivedMessage:
    """The fields of a received message event this channel acts on."""

    event_id: str
    message_id: str
    chat_id: str
    chat_type: str
    sender_open_id: str
    sender_type: str
    message_type: str
    content: dict[str, Any]
    mentions: list[Any] = field(default_factory=list)
    parent_id: str = ""


@dataclass
class ResolvedPayload:
    """Text, downloaded media and metadata of one inbound message."""

    text: str
    media: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


def parse_receive_event(envelope: dict[str, Any]) -> ReceivedMessage | None:
    """Extracts a received message from a raw event envelope, if well formed."""
    event = as_dict(envelope.get("event"))
    message = as_dict(event.get("message"))
    sender = as_dict(event.get("sender"))
    message_id = str(message.get("message_id") or "").strip()
    chat_id = str(message.get("chat_id") or "").strip()
    if not message_id or not chat_id:
        return None
    return ReceivedMessage(
        event_id=str(as_dict(envelope.get("header")).get("event_id") or "").strip(),
        message_id=message_id,
        chat_id=chat_id,
        chat_type=str(message.get("chat_type") or "").strip(),
        sender_open_id=str(
            as_dict(sender.get("sender_id")).get("open_id") or ""
        ).strip(),
        sender_type=str(sender.get("sender_type") or "").strip(),
        message_type=str(message.get("message_type") or "").strip(),
        content=load_json_object(str(message.get("content") or "")),
        mentions=as_list(message.get("mentions")),
        parent_id=str(message.get("parent_id") or "").strip(),
    )


class InboundResolver:
    """Downloads attachments and quoted messages for received events."""

    def __init__(self, api: FeishuApi, attachments: AttachmentStore) -> None:
        self._api = api
        self._attachments = attachments

    async def resolve(self, message: ReceivedMessage) -> ResolvedPayload:
        """Resolves the message body, then merges the quoted message if any."""
        text, media = await self._body(
            message.message_id,
            message.message_type,
            message.content,
            message.mentions,
        )
        payload = ResolvedPayload(text=text, media=media)
        if message.parent_id:
            await self._merge_parent(payload, message.parent_id)
        return payload

    async def _body(
        self,
        message_id: str,
        message_type: str,
        content: dict[str, Any],
        mentions: list[Any] | None = None,
    ) -> tuple[str, list[str]]:
        if message_type == "text":
            return extract_text(content, mentions), []
        if message_type == "post":
            text, image_keys = extract_post(content)
            media = [
                path
                for key in image_keys
                if (path := await self._download(message_id, key, "image"))
            ]
            return text or "[富文本]", media
        if message_type == "image":
            path = await self._download(
                message_id, str(content.get("image_key") or ""), "image"
            )
            return "[图片]", [path] if path else []
        if message_type == "file":
            name = str(content.get("file_name") or "file")
            path = await self._download(
                message_id,
                str(content.get("file_key") or ""),
                "file",
                PurePath(name).suffix,
            )
            return f"[文件: {name}]", [path] if path else []
        if message_type == "interactive":
            return extract_card_text(content) or "[卡片]", []
        return f"[{message_type or '未知'}消息]", []

    async def _merge_parent(self, payload: ResolvedPayload, parent_id: str) -> None:
        payload.metadata["reply_to_message_id"] = parent_id
        try:
            item = await self._api.get_message(parent_id)
        except Exception as error:
            logger.warning("[feishu] 拉取被回复消息失败 id=%s: %s", parent_id, error)
            return
        body = load_json_object(str(as_dict(item.get("body")).get("content") or ""))
        text, media = await self._body(
            parent_id,
            str(item.get("msg_type") or ""),
            body,
            as_list(item.get("mentions")),
        )
        from_bot = as_dict(item.get("sender")).get("sender_type") == "app"
        sender_label = "你（机器人）" if from_bot else "用户"
        payload.metadata["reply_to_sender"] = sender_label
        payload.text = build_inbound_text_with_reply_context(
            user_text=payload.text,
            reply_text=text,
            reply_sender=sender_label,
        )
        payload.media.extend(media)

    async def _download(
        self, message_id: str, key: str, resource_type: str, suffix: str = ""
    ) -> str | None:
        if not key:
            return None
        try:
            data = await self._api.download_resource(message_id, key, resource_type)
        except Exception as error:
            logger.warning("[feishu] 资源下载失败 key=%s: %s", key, error)
            return None
        if resource_type == "image":
            mime = detect_image_mime_from_header(data[:64]) or ""
            suffix = IMAGE_SUFFIXES.get(mime, ".img")
        path = self._attachments.write_bytes(
            data, prefix=f"feishu_{resource_type}_", suffix=suffix
        )
        return str(path)
