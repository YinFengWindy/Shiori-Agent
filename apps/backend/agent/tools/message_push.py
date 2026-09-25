"""
统一消息推送工具，agent 通过 channel + chat_id 向任意已注册渠道发送消息、文件或图片。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from agent.tools.base import Tool
from bus.event_bus import EventBus
from bus.events_lifecycle import ExternalImagePushed
from core.common.runtime_scope import current_runtime_lease

logger = logging.getLogger(__name__)

# Identity is supplied by the host outbound owner, never by model JSON arguments.
PENDING_TURN_DELIVERY = object()

# A sender returns the platform id of the message it just sent, or None when the
# transport exposes no such id. Blank ids are normalized to None on receipt.
SenderResult = str | None


@dataclass(frozen=True)
class PushOutcome:
    """Model-facing result text plus the platform ids the senders reported.

    ``external_message_ids`` lists, in send order, every nonblank id a sender
    returned; channels that cannot report ids contribute nothing.
    """

    text: str
    external_message_ids: tuple[str, ...] = ()


class MessagePushTool(Tool):
    name = "message_push"
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "目标渠道原名，只能取工具描述里列出的可用渠道。",
            },
            "chat_id": {
                "type": "string",
                "description": "目标会话 ID，格式见工具描述里对应渠道的说明。",
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
        self._senders: dict[str, dict[str, Callable[..., Awaitable[SenderResult]]]] = {}
        self._descriptions: dict[str, str] = {}
        self._target_resolvers: dict[str, Callable[[str], str]] = {}
        self._role_target_validator: Callable[[str, str, str], bool | str] | None = None
        self._event_bus = event_bus
        self._transport_lock: asyncio.Lock | None = None
        self._retired_channels: set[str] = set()

    @property
    def description(self) -> str:
        """Lists only the channels registered now, each with its own target hint."""
        available = [
            (
                f"{channel}（{hint}）"
                if (hint := self._descriptions.get(channel))
                else channel
            )
            for channel in self._senders
            if channel not in self._retired_channels
        ]
        return (
            "向指定渠道的用户主动发送消息、文件或图片。"
            "需要提供当前会话对应的渠道名和目标 chat_id。"
            "渠道名必须使用渠道原名，当前可用渠道："
            f"{'、'.join(available) if available else '（无）'}。"
            "message/file/image 三者至少提供一个。"
        )

    def set_transport_lock(self, lock: asyncio.Lock) -> None:
        """Shares the bus handover barrier so direct sends drain before disconnect."""
        self._transport_lock = lock

    def unregister_channel(self, channel: str, *, text: Callable | None = None) -> None:
        """Removes only the sender registration owned by the stopping connection."""
        senders = self._senders.get(channel)
        if senders is None or (text is not None and senders.get("text") != text):
            return
        self._senders.pop(channel, None)
        self._descriptions.pop(channel, None)
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
        text: Callable[[str, str], Awaitable[SenderResult]] | None = None,
        stream_text: Callable[[str, str], Awaitable[SenderResult]] | None = None,
        file: Callable[[str, str, str | None], Awaitable[SenderResult]] | None = None,
        image: Callable[[str, str], Awaitable[SenderResult]] | None = None,
        target_resolver: Callable[[str], str] | None = None,
        text_with_metadata: (
            Callable[[str, str, dict[str, object]], Awaitable[SenderResult]] | None
        ) = None,
        image_with_metadata: (
            Callable[[str, str, dict[str, object]], Awaitable[SenderResult]] | None
        ) = None,
        description: str = "",
    ) -> None:
        """注册渠道的各类 sender。
        - text(chat_id, message)
        - stream_text(chat_id, message)
        - file(chat_id, file_path, name=None)
        - image(chat_id, image_path_or_url)
        - target_resolver(chat_id) -> canonical chat_id
        - text_with_metadata(chat_id, message, metadata) preserves delivery ownership
        - description: 渠道身份与 chat_id 格式的简短说明，写进工具描述的可用渠道列表
        每个 sender 可返回平台为本次发送分配的消息 id（str）供投递记录使用；
        拿不到 id 的渠道返回 None。
        """
        self._senders[channel] = {}
        if description.strip():
            self._descriptions[channel] = description.strip()
        else:
            self._descriptions.pop(channel, None)
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
        return (await self.push(**kwargs)).text

    async def push(self, **kwargs: Any) -> PushOutcome:
        """Sends like ``execute`` and also returns the sender-reported message ids.

        Host-owned delivery (formal proactive turns) needs the ids to record
        delivery on the committed message; the model only ever sees the text.
        """
        if self._transport_lock is None:
            return await self._execute_send(**kwargs)
        async with self._transport_lock:
            return await self._execute_send(**kwargs)

    @staticmethod
    def _has_retired_transport(channel: str) -> bool:
        # A retired transport only serves work its own runtime generation accepted.
        lease = current_runtime_lease()
        return lease is not None and channel in lease.channel_names

    async def _execute_send(self, **kwargs: Any) -> PushOutcome:
        channel: str = kwargs["channel"]
        if channel in self._retired_channels and not self._has_retired_transport(
            channel
        ):
            return PushOutcome(f"渠道 {channel!r} 已停用")
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
            return PushOutcome("错误：message、file、image 至少提供一个")

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
            return PushOutcome(f"发送失败：{e}")

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
            return PushOutcome(
                f"渠道 {channel!r} 未注册，可用渠道：{list(self._senders) or ['（无）']}"
            )

        # Reject unsupported payloads together, before sending any supported part.
        # Otherwise partial success could commit text or media that was never sent.
        unsupported = [
            f"渠道 {channel!r} 不支持发送{label}"
            for payload, label, capabilities in (
                (message, "文本", ("text_with_metadata", "stream_text", "text")),
                (file, "文件", ("file",)),
                (image, "图片", ("image_with_metadata", "image")),
            )
            if payload and not any(name in senders for name in capabilities)
        ]
        if unsupported:
            return PushOutcome("发送失败：" + "；".join(unsupported))

        results: list[str] = []
        external_ids: list[str] = []

        def record_external_id(sent: SenderResult) -> None:
            message_id = _normalize_message_id(sent)
            if message_id is not None:
                external_ids.append(message_id)

        image_sent = False
        try:
            if message:
                if "text_with_metadata" in senders:
                    record_external_id(
                        await senders["text_with_metadata"](
                            chat_id,
                            message,
                            delivery_metadata,
                        )
                    )
                else:
                    sender_name = "stream_text" if "stream_text" in senders else "text"
                    record_external_id(await senders[sender_name](chat_id, message))
                preview = message[:60] + "..." if len(message) > 60 else message
                logger.info(f"[message_push] {channel}:{chat_id} ← text: {preview!r}")
                results.append("文本已发送")

            if file:
                import os

                name = os.path.basename(file)
                record_external_id(await senders["file"](chat_id, file, name))
                logger.info(f"[message_push] {channel}:{chat_id} ← file: {file!r}")
                results.append(f"文件 {name!r} 已发送")

            if image:
                if "image_with_metadata" in senders:
                    record_external_id(
                        await senders["image_with_metadata"](
                            chat_id, image, delivery_metadata
                        )
                    )
                else:
                    record_external_id(await senders["image"](chat_id, image))
                logger.info(f"[message_push] {channel}:{chat_id} ← image: {image!r}")
                results.append("图片已发送")
                image_sent = True

        except Exception as e:
            logger.error(f"[message_push] 发送失败 {channel}:{chat_id}: {e}")
            return PushOutcome(f"发送失败：{e}")

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

        return PushOutcome(
            "；".join(results) if results else f"渠道 {channel!r} 没有可用的 sender",
            tuple(external_ids),
        )


def _normalize_message_id(sent: SenderResult) -> str | None:
    """The single place a sender result becomes an id: blank means no id."""
    return (sent.strip() or None) if sent is not None else None


def _nonblank_payload(value: str | None) -> str | None:
    # Preserve meaningful text formatting and paths; only empty fields are absent.
    return value if value and value.strip() else None


def _is_truthy(value: object) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}
