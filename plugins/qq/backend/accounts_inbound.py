"""Normalize one account's NapCat message into source-aware host input."""

from __future__ import annotations

from typing import Any

from shiori_sdk.messages import InboundMessage
from shiori_sdk.accounts import VIA_ACCOUNT_KEY
from shiori_sdk.channels.message_source import (
    MENTIONED_IDS_KEY,
    MENTIONED_KEY,
    SENDER_NAME_KEY,
)

from .accounts_actions import qq_number, qq_sender_name
from .channel.group_filter import at_member_ids

# Metadata flag of a private message that came through a group temporary
# session (NapCat ``sub_type == "group"``) rather than a real private chat.
GROUP_TEMPORARY_KEY = "group_temporary"


def is_real_private_chat(message: InboundMessage) -> bool:
    """Whether ``message`` is from a real private chat, not a group temp session."""
    metadata = message.metadata or {}
    return metadata.get("chat_type") == "private" and not metadata.get(
        GROUP_TEMPORARY_KEY
    )


def inbound_message(
    *,
    account_id: str,
    expected_uin: str,
    via_account: dict[str, str],
    event: dict[str, Any],
) -> InboundMessage | None:
    """Rejects other-account events and preserves actual chat/member IDs.

    ``via_account`` is the receiving account's snapshot for the host to store.
    """
    if event.get("post_type") != "message":
        return None
    if str(event.get("self_id") or "") != expected_uin:
        return None
    kind = event.get("message_type")
    if kind not in {"private", "group"}:
        return None
    sender = qq_number(event.get("user_id"), "发送者")
    chat_id = (
        sender
        if kind == "private"
        else f"gqq:{qq_number(event.get('group_id'), '群号')}"
    )
    raw = event.get("raw_message")
    content = raw if isinstance(raw, str) else str(event.get("message") or "")
    metadata: dict[str, object] = {
        "account_id": account_id,
        "platform_account_id": expected_uin,
        "chat_type": kind,
        "sender_id": sender,
        "external_message_id": str(event.get("message_id") or ""),
        VIA_ACCOUNT_KEY: via_account,
    }
    sender_name = qq_sender_name(event.get("sender"))
    if sender_name:
        metadata[SENDER_NAME_KEY] = sender_name
    if kind == "private" and event.get("sub_type") == "group":
        metadata[GROUP_TEMPORARY_KEY] = True
    if kind == "group":
        metadata["group_id"] = chat_id[4:]
        # The @ segments are stripped from the text after admission, so the
        # mentioned members are kept here as metadata.
        mentioned_ids = at_member_ids(content)
        metadata[MENTIONED_KEY] = expected_uin in mentioned_ids
        if mentioned_ids:
            metadata[MENTIONED_IDS_KEY] = list(mentioned_ids)
    return InboundMessage(
        channel="qq",
        sender=sender,
        chat_id=chat_id,
        content=content,
        metadata=metadata,
    )
