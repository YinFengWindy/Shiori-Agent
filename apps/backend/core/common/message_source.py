"""Per-message platform provenance, independent of role-session routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from core.accounts.models import VIA_ACCOUNT_KEY, ViaAccount

if TYPE_CHECKING:
    from bus.events import InboundMessage

_PREFIX = "[消息来源: "
# Inbound metadata flag the channel hub sets when the sender is a platform
# identity bound to the desktop user; plugins never set it themselves.
SENDER_IS_USER_KEY = "sender_is_user"
# How the source prefix names a sender who is the desktop user.
USER_SENDER_LABEL = "你的用户"
# Inbound metadata contract for plugins: the platform's display names at the
# time the message arrived. ``GROUP_NAME_KEY`` is the group chat's name;
# ``SENDER_NAME_KEY`` is the sender's display name (group card or nickname).
# Both are optional snapshots, stored with the message and never refreshed.
GROUP_NAME_KEY = "group_name"
SENDER_NAME_KEY = "sender_name"
_TIME_PREFIX = "[当前消息时间:"


def _identifier(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value).strip() or None


def display_name(value: object) -> str | None:
    """Normalize a plugin-reported display name; anything but text is unknown.

    The one place names from ``GROUP_NAME_KEY`` / ``SENDER_NAME_KEY`` are
    stripped, so plugins may pass the platform's raw strings.
    """
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _via_account_prefix(metadata: Mapping[str, Any]) -> str | None:
    """The plugin's 「经由账号」 text; messages stored before snapshots have none."""
    if VIA_ACCOUNT_KEY not in metadata:
        return None
    return ViaAccount.from_metadata(metadata[VIA_ACCOUNT_KEY]).prefix


@dataclass(frozen=True)
class MessageSource:
    """Immutable origin; channel and sender_id form a future member-profile key."""

    channel: str | None = None
    chat_id: str | None = None
    chat_type: str | None = None
    sender_id: str | None = None
    session_key: str | None = None
    # Plugin-formatted text of the account the message came through; the
    # snapshot itself is stored under ``VIA_ACCOUNT_KEY``, not in this record.
    via_account: str | None = None
    # The sender is a platform identity bound to the desktop user.
    sender_is_user: bool = False
    # Display-name snapshots the plugin reported with this message.
    group_name: str | None = None
    sender_name: str | None = None

    @classmethod
    def from_inbound(cls, message: InboundMessage) -> MessageSource:
        """Capture platform fields, never mutable prompt-context aliases."""
        return cls(
            channel=_identifier(message.channel),
            chat_id=_identifier(message.chat_id),
            chat_type=_identifier(message.metadata.get("chat_type")),
            sender_id=_identifier(message.sender),
            session_key=_identifier(message.session_key),
            via_account=_via_account_prefix(message.metadata),
            sender_is_user=message.metadata.get(SENDER_IS_USER_KEY) is True,
            group_name=display_name(message.metadata.get(GROUP_NAME_KEY)),
            sender_name=display_name(message.metadata.get(SENDER_NAME_KEY)),
        )

    @classmethod
    def from_metadata(
        cls, metadata: Mapping[str, Any], *, session_key: str
    ) -> MessageSource:
        """Reconstruct only recorded provenance; missing legacy fields stay unknown."""
        saved = metadata.get("message_source")
        if isinstance(saved, dict):
            return cls(
                channel=_identifier(saved.get("channel")),
                chat_id=_identifier(saved.get("chat_id")),
                chat_type=_identifier(saved.get("chat_type")),
                sender_id=_identifier(saved.get("sender_id")),
                session_key=_identifier(saved.get("session_key")),
                via_account=_via_account_prefix(metadata),
                sender_is_user=saved.get(SENDER_IS_USER_KEY) is True,
                group_name=display_name(saved.get(GROUP_NAME_KEY)),
                sender_name=display_name(saved.get(SENDER_NAME_KEY)),
            )
        return cls(
            channel=_identifier(metadata.get("transport_channel")),
            chat_id=_identifier(metadata.get("transport_chat_id")),
            chat_type=_identifier(metadata.get("chat_type")),
            sender_id=_identifier(metadata.get("sender_id")),
            session_key=session_key,
            via_account=_via_account_prefix(metadata),
            sender_is_user=metadata.get(SENDER_IS_USER_KEY) is True,
        )

    def to_metadata(self) -> dict[str, str | bool | None]:
        """Serialize the captured source for durable per-message storage.

        The user flag is stored only when set, so it stays with the message
        after the identity is unbound.
        """
        stored: dict[str, str | bool | None] = {**self.platform_fields()}
        if self.sender_is_user:
            stored[SENDER_IS_USER_KEY] = True
        return stored

    def platform_fields(self) -> dict[str, str | None]:
        """The platform provenance shown to the model as JSON.

        Display names appear only when captured, so messages stored without
        them keep their exact prefix.
        """
        fields: dict[str, str | None] = {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "chat_type": self.chat_type,
            "sender_id": self.sender_id,
            "session_key": self.session_key,
        }
        if self.group_name:
            fields[GROUP_NAME_KEY] = self.group_name
        if self.sender_name:
            fields[SENDER_NAME_KEY] = self.sender_name
        return fields


def with_message_source(
    content: str | list[dict[str, Any]], source: MessageSource
) -> str | list[dict[str, Any]]:
    """Add one source envelope without altering cached text or media blocks.

    A sender bound to the desktop user is named as such, and a message that
    came through a plugin account also names the account:
    ``[消息来源: {...}；发送者: 你的用户；经由账号: <plugin prefix>]``.
    """
    fields = json.dumps(source.platform_fields(), ensure_ascii=False)
    sender = f"；发送者: {USER_SENDER_LABEL}" if source.sender_is_user else ""
    via = f"；经由账号: {source.via_account}" if source.via_account else ""
    header = f"{_PREFIX}{fields}{sender}{via}]\n"
    if isinstance(content, str):
        return _with_text_source(content, header)
    blocks = [dict(block) for block in content]
    for block in blocks:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            block["text"] = _with_text_source(block["text"], header)
            return blocks
    return [*blocks, {"type": "text", "text": header}]


def _with_text_source(content: str, header: str) -> str:
    if content.startswith(_TIME_PREFIX):
        stamp, separator, text = content.partition("\n")
        if text.startswith(header):
            text = text[len(header) :]
        return stamp + separator + header + text
    if content.startswith(header):
        content = content[len(header) :]
    return header + content
