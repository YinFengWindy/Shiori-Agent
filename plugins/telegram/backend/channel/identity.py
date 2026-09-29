"""Telegram message subjects and topic metadata."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.common.channel_chat_types import is_group_chat_type
from core.common.message_source import GROUP_NAME_KEY, SENDER_NAME_KEY

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


def message_names(chat: object, subject: object) -> dict[str, str]:
    """The group's title and the sender's display name, as the host reads them.

    ``subject`` is ``message_subject``'s sender: a user's full name, or an
    anonymous sender chat's title. Unknown names are left out.
    """
    names: dict[str, str] = {}
    title = str(getattr(chat, "title", "") or "").strip()
    if title and is_group_chat_type(getattr(chat, "type", None)):
        names[GROUP_NAME_KEY] = title
    sender = str(
        getattr(subject, "full_name", "") or getattr(subject, "title", "") or ""
    ).strip()
    if sender:
        names[SENDER_NAME_KEY] = sender
    return names


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
