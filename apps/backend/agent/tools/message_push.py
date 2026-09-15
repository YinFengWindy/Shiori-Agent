"""
统一消息推送工具，agent 通过 channel + chat_id 向任意已注册渠道发送消息、文件或图片。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent.tools.base import Tool
from bus.event_bus import EventBus
from bus.events_lifecycle import ExternalImagePushed
from core.common.runtime_scope import current_runtime_lease

logger = logging.getLogger(__name__)

# Identity is supplied by the host outbound owner, never by model JSON arguments.
PENDING_TURN_DELIVERY = object()


class MessagePushTool(Tool):
    name = "message_push"
    description = (
        "向指定渠道的用户主动发送消息、文件或图片。"
        "需要提供当前会话对应的渠道名和目标 chat_id。"
        "渠道名必须使用渠道原名：desktop（桌面端）、telegram、qq（NapCat QQ）或 qqbot（官方 QQBot）；"
        "桌面端使用 channel=desktop，chat_id 使用当前角色会话 ID（role:<角色ID>）。"
        "官方 QQBot 不能写成 qq。QQBot 私聊 chat_id 格式为 c2c:<user_openid>。"
        "message/file/image 三者至少提供一个。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": (
                    "目标渠道原名：desktop（桌面端）、telegram、qq（NapCat QQ）或 qqbot（官方 QQBot）。"
                    "官方 QQBot 必须填写 qqbot，不能填写 qq。"
                ),
            },
            "chat_id": {
                "type": "string",
                "description": (
                    "目标会话 ID；桌面端使用当前角色会话 ID（role:<角色ID>）；"
                    "官方 QQBot 私聊使用 c2c:<user_openid>"
                ),
            },
            "message": {
                "type": "string",
                "description": "要发送的文本内容（可与 file/image 同时提供）",
            },
            "file": {
                "type": "string",
                "description": "要发送的文件本地路径，例如 /tmp/report.pdf",
            },
            "image": {
                "type": "string",
                "description": "要发送的图片本地路径或 URL",
            },
        },
        "required": ["channel", "chat_id"],
    }

    def __init__(self, event_bus: EventBus | None = None) -> None:
        # channel -> {type: sender_fn}
        self._senders: dict[str, dict[str, Callable[..., Awaitable[None]]]] = {}
        self._target_resolvers: dict[str, Callable[[str], str]] = {}
        self._role_target_validator: Callable[[str, str, str], bool | str] | None = None
        self._event_bus = event_bus
        self._transport_lock: asyncio.Lock | None = None
        self._retired_channels: set[str] = set()

    def set_transport_lock(self, lock: asyncio.Lock) -> None:
        """Shares the bus handover barrier so direct sends drain before disconnect."""
        self._transport_lock = lock

    def unregister_channel(self, channel: str, *, text: Callable | None = None) -> None:
        """Removes only the sender registration owned by the stopping connection."""
        senders = self._senders.get(channel)
        if senders is None or (text is not None and senders.get("text") != text):
            return
        self._senders.pop(channel, None)
        self._target_resolvers.pop(channel, None)
        self._retired_channels.discard(channel)

    def retire_channel(self, channel: str) -> None:
        """Restricts a removed transport to tasks accepted while it was configured."""
        self._retired_channels.add(channel)

    def set_role_target_validator(
        self,
        validator: Callable[[str, str, str], bool | str],
    ) -> None:
        """Registers the authoritative binding check for role-scoped sends.

        A string result is treated as an actionable validation error and is
        surfaced unchanged, allowing callers to distinguish a wrong channel
        from a genuinely unbound target without silently rewriting it.
        """

        self._role_target_validator = validator

    def register_channel(
        self,
        channel: str,
        text: Callable[[str, str], Awaitable[None]] | None = None,
        stream_text: Callable[[str, str], Awaitable[None]] | None = None,
        file: Callable[[str, str, str | None], Awaitable[None]] | None = None,
        image: Callable[[str, str], Awaitable[None]] | None = None,
        target_resolver: Callable[[str], str] | None = None,
        text_with_metadata: (
            Callable[[str, str, dict[str, object]], Awaitable[None]] | None
        ) = None,
        image_with_metadata: (
            Callable[[str, str, dict[str, object]], Awaitable[None]] | None
        ) = None,
    ) -> None:
        """注册渠道的各类 sender。
        - text(chat_id, message)
        - stream_text(chat_id, message)
        - file(chat_id, file_path, name=None)
        - image(chat_id, image_path_or_url)
        - target_resolver(chat_id) -> canonical chat_id
        - text_with_metadata(chat_id, message, metadata) preserves delivery ownership
        """
        self._senders[channel] = {}
        self._retired_channels.discard(channel)
        if text:
            self._senders[channel]["text"] = text
        if stream_text:
            self._senders[channel]["stream_text"] = stream_text
        if text_with_metadata:
            self._senders[channel]["text_with_metadata"] = text_with_metadata
        if image_with_metadata:
            self._senders[channel]["image_with_metadata"] = image_with_metadata
        if file:
            self._senders[channel]["file"] = file
        if image:
            self._senders[channel]["image"] = image
        if target_resolver is not None:
            self._target_resolvers[channel] = target_resolver
        else:
            self._target_resolvers.pop(channel, None)
        logger.debug(
            f"message_push: 注册渠道 {channel!r}  支持: {list(self._senders[channel])}"
        )

    async def execute(self, **kwargs: Any) -> str:
        """Sends nonblank payload fields and reports validation or transport errors."""
        if self._transport_lock is None:
            return await self._execute_send(**kwargs)
        async with self._transport_lock:
            return await self._execute_send(**kwargs)

    @staticmethod
    def _has_retired_transport(channel: str) -> bool:
        lease = current_runtime_lease()
        if lease is None:
            return False
        channels = lease.config.channels
        if channels.telegram is not None and channel == channels.telegram.channel_name:
            return True
        if channels.qq is not None and channel == "qq":
            return True
        manager = lease.core.plugin_manager
        return manager is not None and any(
            item.name == channel for item in manager.channels
        )

    async def _execute_send(self, **kwargs: Any) -> str:
        channel: str = kwargs["channel"]
        if channel in self._retired_channels and not self._has_retired_transport(
            channel
        ):
            return f"渠道 {channel!r} 已停用"
        requested_chat_id = str(kwargs["chat_id"])
        message = _nonblank_payload(kwargs.get("message"))
        file = _nonblank_payload(kwargs.get("file"))
        image = _nonblank_payload(kwargs.get("image"))
        role_id = str(kwargs.get("role_id") or "").strip()
        session_key = str(kwargs.get("session_key") or "").strip()
        pending_commit = kwargs.get("_pending_turn_delivery") is PENDING_TURN_DELIVERY
        delivery_metadata = {
            "delivery_key": str(kwargs.get("push_delivery_key") or "").strip(),
            "already_persisted": _is_truthy(
                kwargs.get("push_message_already_persisted")
            ),
            **({"pending_commit": True} if pending_commit else {}),
        }

        if not message and not file and not image:
            return "错误：message、file、image 至少提供一个"

        try:
            resolver = self._target_resolvers.get(channel)
            chat_id = (
                resolver(requested_chat_id)
                if resolver is not None
                else requested_chat_id
            )
        except Exception as e:
            logger.error(
                f"[message_push] 目标解析失败 {channel}:{requested_chat_id}: {e}"
            )
            return f"发送失败：{e}"

        if role_id and self._role_target_validator is not None:
            validation = self._role_target_validator(role_id, channel, chat_id)
            if validation is not True:
                detail = (
                    validation
                    if isinstance(validation, str)
                    else (
                        f"角色 {role_id} 未绑定目标渠道: {channel}:{requested_chat_id}"
                    )
                )
                raise PermissionError(detail)

        senders = self._senders.get(channel)
        if senders is None:
            return f"渠道 {channel!r} 未注册，可用渠道：{list(self._senders) or ['（无）']}"

        results: list[str] = []
        image_sent = False
        try:
            if message and any(
                name in senders
                for name in ("text_with_metadata", "stream_text", "text")
            ):
                if "text_with_metadata" in senders:
                    await senders["text_with_metadata"](
                        chat_id,
                        message,
                        delivery_metadata,
                    )
                else:
                    sender_name = "stream_text" if "stream_text" in senders else "text"
                    await senders[sender_name](chat_id, message)
                preview = message[:60] + "..." if len(message) > 60 else message
                logger.info(f"[message_push] {channel}:{chat_id} ← text: {preview!r}")
                results.append("文本已发送")

            if file:
                if "file" not in senders:
                    results.append(f"渠道 {channel!r} 不支持发送文件")
                else:
                    import os

                    name = os.path.basename(file)
                    await senders["file"](chat_id, file, name)
                    logger.info(f"[message_push] {channel}:{chat_id} ← file: {file!r}")
                    results.append(f"文件 {name!r} 已发送")

            if image:
                if "image" not in senders and "image_with_metadata" not in senders:
                    results.append(f"渠道 {channel!r} 不支持发送图片")
                else:
                    if "image_with_metadata" in senders:
                        await senders["image_with_metadata"](
                            chat_id, image, delivery_metadata
                        )
                    else:
                        await senders["image"](chat_id, image)
                    logger.info(
                        f"[message_push] {channel}:{chat_id} ← image: {image!r}"
                    )
                    results.append("图片已发送")
                    image_sent = True

        except Exception as e:
            logger.error(f"[message_push] 发送失败 {channel}:{chat_id}: {e}")
            return f"发送失败：{e}"

        if (
            image_sent
            and image
            and channel != "desktop"
            and role_id
            and session_key
            and self._event_bus is not None
            and not pending_commit
        ):
            _ = await self._event_bus.emit(
                ExternalImagePushed(
                    session_key=session_key,
                    role_id=role_id,
                    channel=channel,
                    chat_id=chat_id,
                    image=image,
                    attach_to_turn=_is_truthy(kwargs.get("defer_push_session_sync")),
                    already_persisted=_is_truthy(
                        kwargs.get("push_message_already_persisted")
                    ),
                )
            )

        return "；".join(results) if results else f"渠道 {channel!r} 没有可用的 sender"


def _nonblank_payload(value: str | None) -> str | None:
    # Preserve meaningful text formatting and paths; only empty fields are absent.
    return value if value and value.strip() else None


def _is_truthy(value: object) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}
