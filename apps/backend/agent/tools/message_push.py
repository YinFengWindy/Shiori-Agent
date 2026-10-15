"""
统一消息推送工具，agent 通过 channel + chat_id 向已注册渠道发送消息、文件或图片。

角色只能推送到自己的桌面会话；外部渠道发送走 account_send。
"""

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from shiori_sdk.tools import Tool

logger = logging.getLogger(__name__)

# Identity is supplied by the host outbound owner, never by model JSON arguments.
PENDING_TURN_DELIVERY = object()

# A sender returns the platform id of the message it just sent, or None when the
# transport exposes no such id. Blank ids are normalized to None on receipt.
SenderResult = str | None

# The authoritative binding check for role-scoped sends: (role_id, channel,
# chat_id) -> True to allow. Any other result rejects the send; a string is an
# actionable error surfaced unchanged, so a wrong channel is told apart from a
# genuinely unbound target without silently rewriting it.
RoleTargetValidator = Callable[[str, str, str], bool | str]

MetadataSender = Callable[[str, str, dict[str, object]], Awaitable[SenderResult]]
FileSender = Callable[[str, str, str | None], Awaitable[SenderResult]]


@dataclass(frozen=True)
class PushOutcome:
    """Model-facing result text plus the platform ids the senders reported.

    ``external_message_ids`` lists, in send order, every nonblank id a sender
    returned; channels that cannot report ids contribute nothing.
    """

    text: str
    external_message_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ChannelSenders:
    text: MetadataSender | None
    image: MetadataSender | None
    file: FileSender | None


class MessagePushTool(Tool):
    name = "message_push"
    # Who is sending and the delivery identity the sender receives belong to
    # the caller's execution context; a model argument of the same name must
    # not bypass the role target check or forge delivery metadata. Only the
    # target (channel, chat_id) and the payload are the model's.
    context_precedence = frozenset(
        {
            "role_id",
            "push_delivery_key",
            "push_message_already_persisted",
            "push_proactive",
            "_pending_turn_delivery",
        }
    )
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

    def __init__(self, *, role_target_validator: RoleTargetValidator) -> None:
        """``role_target_validator`` checks every send that carries a role."""
        self._senders: dict[str, _ChannelSenders] = {}
        self._descriptions: dict[str, str] = {}
        self._role_target_validator = role_target_validator

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
        ]
        return (
            "向指定渠道的用户主动发送消息、文件或图片。"
            "需要提供当前会话对应的渠道名和目标 chat_id。"
            "渠道名必须使用渠道原名，当前可用渠道："
            f"{'、'.join(available) if available else '（无）'}。"
            "message/file/image 三者至少提供一个。"
        )

    def register_channel(
        self,
        channel: str,
        *,
        text_with_metadata: MetadataSender | None = None,
        image_with_metadata: MetadataSender | None = None,
        file: FileSender | None = None,
        description: str = "",
    ) -> None:
        """注册渠道的各类 sender。
        - text_with_metadata(chat_id, message, metadata) preserves delivery ownership
        - image_with_metadata(chat_id, image_path_or_url, metadata)
        - file(chat_id, file_path, name=None)
        - description: 渠道身份与 chat_id 格式的简短说明，写进工具描述的可用渠道列表
        每个 sender 可返回平台为本次发送分配的消息 id（str）供投递记录使用；
        拿不到 id 的渠道返回 None。
        """
        self._senders[channel] = _ChannelSenders(
            text=text_with_metadata, image=image_with_metadata, file=file
        )
        if description.strip():
            self._descriptions[channel] = description.strip()
        else:
            self._descriptions.pop(channel, None)
        logger.debug(f"message_push: 注册渠道 {channel!r}")

    async def execute(self, **kwargs: Any) -> str:
        """Sends nonblank payloads; host-only ``push_proactive=False`` marks supplements.

        The optional intent must be a bool. Omitting it keeps proactive delivery;
        model arguments cannot set it through the tool registry. Supplemental
        delivery supports text and images; files retain their legacy send path.
        Returning at all means every payload was delivered or queued with the
        current turn; a rejected target, unknown channel, unsupported payload or
        sender failure raises.
        """
        return (await self.push(**kwargs)).text

    async def push(self, **kwargs: Any) -> PushOutcome:
        """Sends like ``execute`` and also returns the sender-reported message ids.

        Host-owned delivery (formal proactive turns) needs the ids to record
        delivery on the committed message; the model only ever sees the text.
        """
        proactive = kwargs.get("push_proactive", True)
        if not isinstance(proactive, bool):
            raise ValueError("push_proactive must be a bool")
        channel: str = kwargs["channel"]
        chat_id = str(kwargs["chat_id"])
        message = _nonblank_payload(kwargs.get("message"))
        file = _nonblank_payload(kwargs.get("file"))
        image = _nonblank_payload(kwargs.get("image"))
        if not proactive and file:
            raise ValueError("push_proactive=False does not support file payloads")
        role_id = str(kwargs.get("role_id") or "").strip()
        pending_commit = kwargs.get("_pending_turn_delivery") is PENDING_TURN_DELIVERY
        delivery_metadata = {
            "delivery_key": str(kwargs.get("push_delivery_key") or "").strip(),
            "already_persisted": _is_truthy(
                kwargs.get("push_message_already_persisted")
            ),
            **({"pending_commit": True} if pending_commit else {}),
            **({"proactive": False} if not proactive else {}),
        }

        if not message and not file and not image:
            raise ValueError("message、file、image 至少提供一个")

        # The runtime validator only lets a role reach its own desktop session;
        # external role sends go through account_send, which records them.
        if role_id:
            validation = self._role_target_validator(role_id, channel, chat_id)
            if validation is not True:
                detail = (
                    validation
                    if isinstance(validation, str)
                    else f"角色 {role_id} 未绑定目标渠道: {channel}:{chat_id}"
                )
                raise PermissionError(detail)

        senders = self._senders.get(channel)
        if senders is None:
            raise ValueError(
                f"渠道 {channel!r} 未注册，可用渠道：{list(self._senders) or ['（无）']}"
            )

        # Reject unsupported payloads together, before sending any supported part.
        # Otherwise partial success could commit text or media that was never sent.
        unsupported = [
            f"渠道 {channel!r} 不支持发送{label}"
            for payload, label, sender in (
                (message, "文本", senders.text),
                (file, "文件", senders.file),
                (image, "图片", senders.image),
            )
            if payload and sender is None
        ]
        if unsupported:
            raise ValueError("；".join(unsupported))

        results: list[str] = []
        external_ids: list[str] = []

        def record_external_id(sent: SenderResult) -> None:
            message_id = _normalize_message_id(sent)
            if message_id is not None:
                external_ids.append(message_id)

        if message and senders.text is not None:
            record_external_id(await senders.text(chat_id, message, delivery_metadata))
            preview = message[:60] + "..." if len(message) > 60 else message
            logger.info(f"[message_push] {channel}:{chat_id} ← text: {preview!r}")
            results.append(
                "文本已排队，回合成功后发送"
                if delivery_metadata.get("queued")
                else "文本已发送"
            )

        if file and senders.file is not None:
            name = os.path.basename(file)
            record_external_id(await senders.file(chat_id, file, name))
            logger.info(f"[message_push] {channel}:{chat_id} ← file: {file!r}")
            results.append(f"文件 {name!r} 已发送")

        if image and senders.image is not None:
            record_external_id(await senders.image(chat_id, image, delivery_metadata))
            logger.info(f"[message_push] {channel}:{chat_id} ← image: {image!r}")
            results.append(
                "图片已排队，回合成功后发送"
                if delivery_metadata.get("queued")
                else "图片已发送"
            )

        return PushOutcome("；".join(results), tuple(external_ids))


def _normalize_message_id(sent: SenderResult) -> str | None:
    """The single place a sender result becomes an id: blank means no id."""
    return (sent.strip() or None) if sent is not None else None


def _nonblank_payload(value: str | None) -> str | None:
    # Preserve meaningful text formatting and paths; only empty fields are absent.
    return value if value and value.strip() else None


def _is_truthy(value: object) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}
