"""Telegram message subjects and topic metadata."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Message


def message_subject(
    message: Message, fallback_user: object | None = None
) -> tuple[object | None, str, str]:
    """Keep anonymous sender chats distinct from Telegram's compatibility user."""
    chat = getattr(message, "sender_chat", None)
    if chat is not None:
        return chat, f"chat:{chat.id}", "chat"
    user = getattr(message, "from_user", None) or fallback_user
    return user, str(user.id) if user else "", "user"


def message_topic_metadata(message: Message) -> dict[str, int]:
    """Preserve Telegram's forum topic target on the received message."""
    thread_id = getattr(message, "message_thread_id", None)
    return {"message_thread_id": thread_id} if thread_id is not None else {}


def message_mentioned_bot(message: Message, username: str) -> bool:
    """Recognize a bot mention in text or media caption without partial names."""
    if not username:
        return False
    content = str(
        getattr(message, "text", None) or getattr(message, "caption", None) or ""
    )
    return re.search(rf"(?<!\w)@{re.escape(username)}(?!\w)", content, re.I) is not None
