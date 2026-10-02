"""Per-message platform provenance, independent of role-session routing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from shiori_sdk.accounts.models import VIA_ACCOUNT_KEY, ViaAccount
from shiori_sdk.channels.chat_types import is_group_chat_type

if TYPE_CHECKING:
    from shiori_sdk.messages import InboundMessage

_PREFIX = "[消息来源: "
# Inbound metadata flag the channel hub sets when the sender is a platform
# identity bound to the desktop user; plugins never set it themselves.
SENDER_IS_USER_KEY = "sender_is_user"
# How the source prefix names a sender who is the desktop user.
USER_SENDER_LABEL = "你的用户"
# How a group message's source prefix names any other sender.
MEMBER_SENDER_LABEL = "群友"
# Inbound metadata contract for plugins: the platform's display names at the
# time the message arrived. ``GROUP_NAME_KEY`` is the group chat's name;
# ``SENDER_NAME_KEY`` is the sender's display name (group card or nickname).
# Both are optional snapshots, stored with the message and never refreshed.
GROUP_NAME_KEY = "group_name"
SENDER_NAME_KEY = "sender_name"
# Optional inbound metadata contract for plugins: the platform member IDs the
# message structurally mentions (@), and the member ID of the message it
# replies to. Plain-text names are never member IDs; leave these unset then.
MENTIONED_IDS_KEY = "mentioned_ids"
REPLY_TO_SENDER_ID_KEY = "reply_to_sender_id"
# Optional inbound metadata of a message that quotes another and starts a
# turn (#555), set through ``shiori_sdk.channels.reply_context.with_reply_quote``:
# the quoted message's text, its sender's display-name snapshot and the local
# files of its pictures, which lead the turn's media in this order. The
# message's own text and media stay what is stored.
REPLY_TO_CONTENT_KEY = "reply_to_content"
REPLY_TO_SENDER_NAME_KEY = "reply_to_sender_name"
REPLY_TO_MEDIA_KEY = "reply_to_media"
# Turn metadata: the user message's text the session stores when the turn's
# content wraps it for the model (a desktop or channel quote). Internal to the
# turn; never kept in the stored message's metadata.
PERSISTED_USER_CONTENT_KEY = "persisted_user_content"
# Inbound metadata flag the channel hub sets when the quoted sender
# (``REPLY_TO_SENDER_ID_KEY``) is a platform identity bound to the desktop
# user; plugins never set it themselves.
REPLY_TO_SENDER_IS_USER_KEY = "reply_to_sender_is_user"
# Inbound metadata flag a plugin sets on a group message that structurally
# mentions (@) the receiving account itself.
MENTIONED_KEY = "mentioned"
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


def _identifiers(value: object) -> tuple[str, ...]:
    """Normalize a plugin-reported member ID list; entries that are not IDs are unknown."""
    if not isinstance(value, list):
        return ()
    ids = (_identifier(item) for item in value)
    return tuple(dict.fromkeys(item for item in ids if item is not None))


def _via_account_prefix(metadata: Mapping[str, Any]) -> str | None:
    """The plugin's 「经由账号」 text; messages stored before snapshots have none."""
    if VIA_ACCOUNT_KEY not in metadata:
        return None
    return ViaAccount.from_metadata(metadata[VIA_ACCOUNT_KEY]).prefix


def addresses_account(metadata: Mapping[str, Any], platform_account_id: str) -> bool:
    """Whether a group message calls on the account ``platform_account_id``.

    It does when the plugin flagged an @ of the account (``MENTIONED_KEY``) or
    the message replies to one the account sent (``REPLY_TO_SENDER_ID_KEY``
    names the account's own platform ID). The only way a group message starts
    a role's turn.
    """
    return metadata.get(MENTIONED_KEY) is True or (
        _identifier(metadata.get(REPLY_TO_SENDER_ID_KEY)) == platform_account_id
    )


@dataclass(frozen=True)
class MessageSource:
    """Immutable origin; channel and sender_id form the member-profile key (#498)."""

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
    # Member IDs the message structurally mentions and the member it replies
    # to, as the plugin reported them; stored with the message. A group
    # message's source prefix lists the mentions; the reply target is not shown.
    mentioned_ids: tuple[str, ...] = ()
    reply_to_sender_id: str | None = None

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
            mentioned_ids=_identifiers(message.metadata.get(MENTIONED_IDS_KEY)),
            reply_to_sender_id=_identifier(
                message.metadata.get(REPLY_TO_SENDER_ID_KEY)
            ),
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
                mentioned_ids=_identifiers(saved.get(MENTIONED_IDS_KEY)),
                reply_to_sender_id=_identifier(saved.get(REPLY_TO_SENDER_ID_KEY)),
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

    def to_metadata(self) -> dict[str, str | bool | list[str] | None]:
        """Serialize the captured source for durable per-message storage.

        The user flag is stored only when set, so it stays with the message
        after the identity is unbound. Mentions and the reply target are
        stored only when reported.
        """
        stored: dict[str, str | bool | list[str] | None] = {**self.platform_fields()}
        if self.sender_is_user:
            stored[SENDER_IS_USER_KEY] = True
        if self.mentioned_ids:
            stored[MENTIONED_IDS_KEY] = list(self.mentioned_ids)
        if self.reply_to_sender_id:
            stored[REPLY_TO_SENDER_ID_KEY] = self.reply_to_sender_id
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

    A message that came through a plugin account also names the account:
    ``[消息来源: {...}<sender>；经由账号: <plugin prefix>]``. The sender item
    is ``_sender_items``'s: in a group every sender is named, the user or a
    group member, with the members the message @s.
    """
    fields = json.dumps(source.platform_fields(), ensure_ascii=False)
    via = f"；经由账号: {source.via_account}" if source.via_account else ""
    header = f"{_PREFIX}{fields}{_sender_items(source)}{via}]\n"
    if isinstance(content, str):
        return _with_text_source(content, header)
    blocks = [dict(block) for block in content]
    for block in blocks:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            block["text"] = _with_text_source(block["text"], header)
            return blocks
    return [*blocks, {"type": "text", "text": header}]


def _sender_items(source: MessageSource) -> str:
    """The source prefix's sender and @ items.

    Outside a group only a sender bound to the desktop user is named
    (``；发送者: 你的用户``), as before #553. In a group every sender is named
    with their member ID, so the model never takes a member for the user:
    ``；发送者: 你的用户（ID 1）`` or ``；发送者: 群友「昵称」（ID 2）`` (just
    ``群友（ID 2）`` without a name snapshot); a message that @s members adds
    ``；@: ID 3、ID 4``, written like the listening block's lines.
    """
    if not is_group_chat_type(source.chat_type):
        return f"；发送者: {USER_SENDER_LABEL}" if source.sender_is_user else ""
    if source.sender_is_user:
        sender = USER_SENDER_LABEL
    elif source.sender_name:
        sender = f"{MEMBER_SENDER_LABEL}「{source.sender_name}」"
    else:
        sender = MEMBER_SENDER_LABEL
    member_id = f"（ID {source.sender_id}）" if source.sender_id else ""
    mentions = (
        f"；@: {'、'.join(f'ID {member}' for member in source.mentioned_ids)}"
        if source.mentioned_ids
        else ""
    )
    return f"；发送者: {sender}{member_id}{mentions}"


def _with_text_source(content: str, header: str) -> str:
    if content.startswith(_TIME_PREFIX):
        stamp, separator, text = content.partition("\n")
        if text.startswith(header):
            text = text[len(header) :]
        return stamp + separator + header + text
    if content.startswith(header):
        content = content[len(header) :]
    return header + content
