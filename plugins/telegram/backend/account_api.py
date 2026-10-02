"""Bot-scoped target discovery and explicit Telegram operations."""

from __future__ import annotations

import re
from collections.abc import Awaitable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telegram.error import NetworkError, TelegramError

from shiori_sdk.rpc import Concurrency
from shiori_sdk.storage import read_mapping

from shiori_sdk.accounts import VIA_ACCOUNT_KEY
from shiori_sdk.media import detect_image_mime_from_header
from shiori_sdk.accounts.targets import (
    ACCOUNT_SEND_METHOD,
    ACCOUNT_TARGETS_METHOD,
    GROUP_MEMBER_TARGET,
    UncertainDeliveryError,
    account_send_media,
)
from .channel.formatting import mention_markdown

if TYPE_CHECKING:
    from shiori_sdk.rpc import RpcCapability
    from shiori_sdk.storage import KeyValueStore
    from .bots import TelegramBots
    from .channel.lifecycle import TelegramChannel


# Image types Telegram accepts as a photo.
_PHOTO_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})


class TelegramAccountApi:
    """Exposes observed chats and permission-limited member lookup per Bot."""

    def __init__(
        self,
        bots: TelegramBots,
        rpc: RpcCapability,
        store: KeyValueStore,
    ) -> None:
        self._bots = bots
        self._rpc = rpc
        self._store = store

    def register(self) -> None:
        self._rpc.register(
            "token.verify", self._bots.verify_token, concurrency=Concurrency.INTEGRATION
        )
        self._rpc.register(
            "identity.get", self.get_identity, concurrency=Concurrency.READ_ONLY
        )
        self._rpc.register(
            "known.list", self.list_known, concurrency=Concurrency.READ_ONLY
        )
        self._rpc.register(
            "member.get", self.get_member, concurrency=Concurrency.READ_ONLY
        )
        self._rpc.register(
            "target.send", self.send_target, concurrency=Concurrency.INTEGRATION
        )
        self._rpc.register(
            ACCOUNT_TARGETS_METHOD,
            self.account_targets,
            concurrency=Concurrency.READ_ONLY,
        )
        self._rpc.register(
            ACCOUNT_SEND_METHOD,
            self.account_send,
            concurrency=Concurrency.INTEGRATION,
        )

    def _ref_for_account(self, payload: dict[str, Any]) -> str:
        return self._bots.ref_for_account(str(payload.get("account_id") or ""))

    async def account_targets(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Adapt the shared query while preserving known-only directory scope."""
        ref = self._ref_for_account(payload)
        kind = str(payload.get("kind") or "")
        if kind == "known":
            return await self.list_known({"ref": ref})
        if kind == "member":
            return await self.get_member(
                {
                    "ref": ref,
                    "chat_id": payload.get("group_id"),
                    "user_id": payload.get("member_id"),
                }
            )
        raise ValueError("Telegram 仅支持已知会话和指定成员查询")

    async def account_send(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate a selected Telegram chat, optional forum topic and mentions.

        Group messages start with a mention of each ``mention_ids`` user;
        images follow the text as separate photos in the same topic. The
        receipt is the first message's and carries the Bot's snapshot.
        """
        ref = self._ref_for_account(payload)
        target_kind = str(payload.get("target_kind") or "")
        target_id = str(payload.get("target_id") or "")
        if target_kind == GROUP_MEMBER_TARGET:
            raise ValueError("Telegram 不支持群临时会话")
        if target_kind not in {"private", "group"} or (
            target_id.startswith("-") != (target_kind == "group")
        ):
            raise ValueError("Telegram 目标类型与会话 ID 不匹配")
        text = str(payload.get("message") or "")
        mentions = payload.get("mention_ids") or []
        if mentions:
            if target_kind != "group":
                raise ValueError("Telegram 只有群消息可以提及成员")
            text = mention_markdown(mentions) + text
        # Taken before sending so a completed send always returns its snapshot.
        via = self._channel({"ref": ref}).via_account()
        result = await self.send_target(
            {
                "ref": ref,
                "chat_id": target_id,
                "text": text,
                "message_thread_id": payload.get("message_thread_id"),
                "media": list(account_send_media(payload)),
            }
        )
        return {**result, VIA_ACCOUNT_KEY: via}

    def _channel(self, payload: dict[str, Any]) -> TelegramChannel:
        channel = self._bots.channel(str(payload.get("ref") or ""))
        if channel is None:
            raise ValueError("Unknown Telegram Bot account")
        return channel

    def _known_ref(self, payload: dict[str, Any]) -> str:
        ref = str(payload.get("ref") or "")
        if re.fullmatch(r"[a-z0-9_]{1,48}", ref) is None:
            raise ValueError("Unknown Telegram Bot account")
        return ref

    async def list_known(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return only chats observed by this Bot, never a full contact list."""
        ref = self._known_ref(payload)
        known = read_mapping(self._store, f"known_chats:{ref}")
        chats = []
        for value in known.values():
            if not isinstance(value, dict):
                raise ValueError("Stored Telegram conversation must be an object")
            chats.append(value)
        return {
            "scope": "known_conversations",
            "chats": sorted(chats, key=lambda item: item["last_seen"], reverse=True),
        }

    async def get_identity(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return the last verified Bot identity without exposing its Token."""
        ref = self._known_ref(payload)
        return read_mapping(self._store, f"identity:{ref}")

    async def get_member(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Query one group member; Telegram may reject it without bot permission."""
        ref = self._known_ref(payload)
        channel = self._channel(payload)
        chat_id = str(payload.get("chat_id") or "")
        user_id = str(payload.get("user_id") or "")
        known = read_mapping(self._store, f"known_chats:{ref}")
        if not chat_id.startswith("-") or chat_id not in known or not user_id.isdigit():
            raise ValueError("A known group and numeric user ID are required")
        try:
            member = await channel.bot.get_chat_member(int(chat_id), int(user_id))
        except TelegramError:
            return {
                "scope": "specific_member",
                "status": "unavailable",
                "reason": "permission_or_platform_limit",
            }
        user = member.user
        return {
            "scope": "specific_member",
            "status": member.status,
            "user_id": str(user.id),
            "name": user.full_name,
            "username": user.username or "",
        }

    async def send_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send text and/or images to one explicit target through the selected Bot."""
        channel = self._channel(payload)
        if not channel.can_send():
            raise RuntimeError("Telegram Bot is not connected")
        chat_id = str(payload.get("chat_id") or "").strip()
        text = str(payload.get("text") or "")
        media = account_send_media(payload)
        topic = payload.get("message_thread_id")
        if not chat_id.lstrip("-").isdigit() or (not text.strip() and not media):
            raise ValueError(
                "A numeric chat ID and message text or images are required"
            )
        if topic is not None and (
            not isinstance(topic, int) or topic <= 0 or not chat_id.startswith("-")
        ):
            raise ValueError("A group topic requires a positive message_thread_id")
        for image in media:
            _check_image(image)
        # Text, then each image as a photo in the same topic; the first ID is
        # the receipt.
        parts = [
            *([(channel.send, text)] if text.strip() else []),
            *((channel.send_image, image) for image in media),
        ]
        receipt = ""
        for send, value in parts:
            try:
                message_id = await _confirmed(
                    send(chat_id, value, message_thread_id=topic)
                )
            except Exception as exc:
                if not receipt:
                    raise
                # The user already has part of the message: not a clean failure.
                raise UncertainDeliveryError(
                    "Telegram 消息已部分送达，后续图片发送失败"
                ) from exc
            receipt = receipt or message_id
        return {"chat_id": chat_id, "message_thread_id": topic, "message_id": receipt}


async def _confirmed(sending: Awaitable[str | None]) -> str:
    """One Telegram message's ID, with lost links and receipts as uncertain."""
    try:
        receipt = await sending
    except NetworkError as exc:
        raise UncertainDeliveryError("Telegram 发送连接中断，结果不确定") from exc
    if not receipt:
        raise UncertainDeliveryError("Telegram 发送未返回消息 ID")
    return receipt


def _check_image(source: str) -> None:
    """Refuses a local image Telegram cannot send before anything is sent.

    URLs pass through; the platform fetches them. A local path must be a
    readable PNG、JPEG、WebP 和 GIF file.
    """
    if source.startswith(("http://", "https://")):
        return
    path = Path(source).expanduser()
    if not path.is_file():
        raise ValueError(f"Telegram 图片文件不存在: {path}")
    try:
        with path.open("rb") as image:
            header = image.read(4096)
    except OSError as exc:
        raise ValueError(f"Telegram 图片文件无法读取: {path}") from exc
    if detect_image_mime_from_header(header) not in _PHOTO_MIME_TYPES:
        raise ValueError(f"Telegram 图片仅支持 PNG、JPEG、WebP 和 GIF: {path}")
