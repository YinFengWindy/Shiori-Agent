"""Plugin RPC names and payload shape for account-scoped targets and sends.

``account.targets`` receives account_id, kind, group_id, and member_id.
``account.send`` receives account_id, message and ``AccountTarget.to_payload()``:
target_kind, target_id, message_thread_id (int or None), group_id (the group
of a ``group_member`` temporary session, else "") and mention_ids (member IDs
to mention in a ``group`` target, possibly empty). The host checks only this
shape; plugins own capability and target validation and must refuse clearly
what their platform cannot do (e.g. mentions or group temporary sessions).
The result carries the platform's actual ``message_id`` and, optionally, the
plugin's ``ViaAccount`` snapshot under ``VIA_ACCOUNT_KEY``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ACCOUNT_TARGETS_METHOD = "account.targets"
ACCOUNT_SEND_METHOD = "account.send"

# A group member reached through a group temporary session; needs group_id.
GROUP_MEMBER_TARGET = "group_member"
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


def _text(value: object, label: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{label} 必须是文本")
    return str(value).strip()


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
        raw_mentions = arguments.get("mention_ids") or []
        if not isinstance(raw_mentions, list):
            raise ValueError("mention_ids 必须是成员 ID 列表")
        mention_ids = tuple(
            dict.fromkeys(_text(item, "mention_ids") for item in raw_mentions)
        )
        if any(not item for item in mention_ids):
            raise ValueError("mention_ids 不能包含空成员 ID")
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
