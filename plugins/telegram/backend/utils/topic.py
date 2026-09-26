"""Typed optional topic argument for Telegram Bot API calls."""

from typing import TypedDict


class TelegramTopicKwargs(TypedDict, total=False):
    """Only the Bot API's forum topic argument may be expanded."""

    message_thread_id: int


def telegram_topic_kwargs(message_thread_id: int | None) -> TelegramTopicKwargs:
    """Omit the argument for a main-chat or private-chat send."""
    return {"message_thread_id": message_thread_id} if message_thread_id else {}
