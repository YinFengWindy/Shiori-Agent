"""Normalize one account's NapCat message into source-aware host input."""

from __future__ import annotations

from typing import Any

from bus.events import InboundMessage

from .accounts_actions import qq_number
from .channel.group_filter import is_at_bot


def inbound_message(
    *, account_id: str, expected_uin: str, event: dict[str, Any]
) -> InboundMessage | None:
    """Rejects other-account events and preserves actual chat/member IDs."""
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
    metadata = {
        "account_id": account_id,
        "platform_account_id": expected_uin,
        "chat_type": kind,
        "sender_id": sender,
        "external_message_id": str(event.get("message_id") or ""),
    }
    if kind == "group":
        metadata["group_id"] = chat_id[4:]
        metadata["mentioned"] = is_at_bot(content, expected_uin)
    return InboundMessage(
        channel="qq",
        sender=sender,
        chat_id=chat_id,
        content=content,
        metadata=metadata,
    )
