"""Resolve who sent the message a QQ group message replies to."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace

from websockets.exceptions import ConnectionClosed

from bus.events import InboundMessage
from core.common.message_source import REPLY_TO_SENDER_ID_KEY

from .channel.group_filter import reply_message_id
from .onebot import OneBotError

logger = logging.getLogger(__name__)

# ``fetch(account_id, message_id)`` returns the QQ number that sent the message.
ReplySenderFetch = Callable[[str, str], Awaitable[str]]


async def with_reply_sender(
    message: InboundMessage, fetch: ReplySenderFetch
) -> InboundMessage:
    """Adds ``REPLY_TO_SENDER_ID_KEY`` to a group message that replies to another.

    The CQ reply segment only carries the replied-to message's ID, so its
    sender is asked from NapCat. The host compares it with the account's own
    QQ number to tell a reply to the role. A failed query (the replied-to
    message expired or was recalled, the account went offline, a timeout)
    only costs the message its reply target: it is logged and the message
    proceeds without one, so it does not count as a reply to the role.
    """
    metadata = message.metadata
    if metadata.get("chat_type") != "group":
        return message
    replied_id = reply_message_id(message.content)
    if replied_id is None:
        return message
    account_id = str(metadata["account_id"])
    try:
        sender = await fetch(account_id, replied_id)
    except (OneBotError, TimeoutError, ConnectionClosed) as exc:
        logger.warning(
            "[qq] 账号 %s 被回复消息 %s 的发送者查询失败，消息不带回复对象: %s",
            account_id,
            replied_id,
            exc,
        )
        return message
    return replace(message, metadata={**metadata, REPLY_TO_SENDER_ID_KEY: sender})
