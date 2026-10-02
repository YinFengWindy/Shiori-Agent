"""Plugin RPC names and payload shape for account-scoped targets and sends.

``account.targets`` receives account_id, kind, group_id, and member_id.
``account.send`` receives account_id, message (possibly empty when media is
not), media (image attachments, see ``account_send_media``) and
``AccountTarget.to_payload()``: target_kind, target_id, message_thread_id (int
or None), group_id (the group of a ``group_member`` temporary session, else "")
and mention_ids (member IDs to mention in a ``group`` target, possibly empty).
The host checks only this shape; plugins own capability and target validation
and must refuse clearly what their platform cannot do (e.g. mentions or group
temporary sessions). The result carries the platform's actual ``message_id``
(the first platform message when text and images go out separately) and,
optionally, the plugin's ``ViaAccount`` snapshot under ``VIA_ACCOUNT_KEY``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from shiori_sdk.channels.chat_types import parse_mention_ids

ACCOUNT_TARGETS_METHOD = "account.targets"
ACCOUNT_SEND_METHOD = "account.send"
# ``account.send`` payload key of the image attachments.
ACCOUNT_SEND_MEDIA_KEY = "media"

# A group member reached through a group temporary session; needs group_id.
GROUP_MEMBER_TARGET = "group_member"
# The desktop user, a model-facing ``account_send`` target kind only: the host
# resolves it from the user's bindings to a private target before sending, so
# plugins never receive it.
USER_TARGET = "user"
# The fields naming a specific target, which a ``user`` target must not carry.
_SPECIFIC_TARGET_KEYS = ("target_id", "message_thread_id", "group_id", "mention_ids")
# The only target kind whose message may mention members.
GROUP_TARGET = "group"


# Model-facing JSON schema of the fields ``AccountTarget.from_arguments`` reads,
# shared by the account_send tool and message_push retargeting.
ACCOUNT_TARGET_PROPERTIES: dict[str, Any] = {
    "target_kind": {
        "type": "string",
        "description": (
            "目标类型：private（私聊）、group（群聊）或 group_member"
            "（群临时会话，需 group_id）；渠道是否支持由其插件校验。"
        ),
    },
    "target_id": {
        "type": "string",
        "description": "目标 ID：私聊对象、群或群成员的平台 ID。",
    },
    "message_thread_id": {"type": "integer", "description": "可选，群话题 ID。"},
    "group_id": {
        "type": "string",
        "description": "仅 group_member 需要：该成员所在群的 ID。",
    },
    "mention_ids": {
        "type": "array",
        "items": {"type": "string"},
        "description": "可选，仅 group 目标：要 @ 的群成员 ID 列表。",
    },
}


class UncertainDeliveryError(RuntimeError):
    """The platform may have accepted a send but did not confirm a receipt."""


def account_send_media(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """The image attachments of an ``account.send`` request, in sending order.

    Each item is a local image file path or an http(s) URL, the same form the
    proactive outbound path produces; a missing key means none. Raises
    ValueError for anything but a list of non-empty strings.
    """
    media = payload.get(ACCOUNT_SEND_MEDIA_KEY)
    if media is None:
        return ()
    if not isinstance(media, list) or any(
        not isinstance(item, str) or not item.strip() for item in media
    ):
        raise ValueError("media 必须是图片路径或 URL 的列表")
    return tuple(item.strip() for item in media)


def _text(value: object, label: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{label} 必须是文本")
    return str(value).strip()


def is_user_target(arguments: Mapping[str, Any]) -> bool:
    """Whether ``arguments`` select the ``user`` target.

    Raises ValueError when they select it but also name a specific target,
    since the host alone decides where the user is reached.
    """
    if _text(arguments.get("target_kind"), "target_kind") != USER_TARGET:
        return False
    extra = [
        key for key in _SPECIFIC_TARGET_KEYS if arguments.get(key) not in (None, "", [])
    ]
    if extra:
        raise ValueError(
            f"target_kind={USER_TARGET} 由宿主按身份绑定解析，不能再指定 {'、'.join(extra)}"
        )
    return True


@dataclass(frozen=True)
class AccountTarget:
    """One explicitly selected account target, checked for shape only."""

    kind: str
    id: str
    message_thread_id: int | None = None
    group_id: str = ""
    mention_ids: tuple[str, ...] = ()

    @classmethod
    def from_arguments(cls, arguments: Mapping[str, Any]) -> AccountTarget:
        """Reads target_kind, target_id, message_thread_id, group_id, mention_ids.

        Raises ValueError for a missing kind or ID, a non-integer topic, a
        ``group_member`` target without ``group_id`` (or a ``group_id`` on any
        other kind), and ``mention_ids`` on anything but a ``group`` target.
        """
        kind = _text(arguments.get("target_kind"), "target_kind")
        target_id = _text(arguments.get("target_id"), "target_id")
        if not kind or not target_id:
            raise ValueError("目标类型和目标 ID 不能为空")
        topic = arguments.get("message_thread_id")
        if topic is not None and (
            isinstance(topic, bool) or not isinstance(topic, int)
        ):
            raise ValueError("message_thread_id 必须是整数")
        group_id = _text(arguments.get("group_id"), "group_id")
        if (kind == GROUP_MEMBER_TARGET) != bool(group_id):
            raise ValueError("group_id 只用于且必须用于 group_member 目标")
        mention_ids = parse_mention_ids(arguments.get("mention_ids"))
        if mention_ids and kind != GROUP_TARGET:
            raise ValueError("mention_ids 仅对 group 目标有效")
        return cls(kind, target_id, topic, group_id, mention_ids)

    def to_payload(self) -> dict[str, Any]:
        """The target fields of an ``account.send`` request."""
        return {
            "target_kind": self.kind,
            "target_id": self.id,
            "message_thread_id": self.message_thread_id,
            "group_id": self.group_id,
            "mention_ids": list(self.mention_ids),
        }
