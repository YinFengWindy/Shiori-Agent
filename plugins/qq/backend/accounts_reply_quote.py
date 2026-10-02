"""The message a QQ message replies to: its sender for routing, its text for the turn."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace

from websockets.exceptions import ConnectionClosed

from shiori_sdk.messages import InboundMessage
from shiori_sdk.channels.message_source import REPLY_TO_SENDER_ID_KEY
from shiori_sdk.channels.reply_context import with_reply_quote

from .accounts_actions import RepliedMessage
from .channel.compat import extract_cq_images
from .channel.group_filter import (
    reply_message_id,
    strip_at_segments,
    strip_reply_segments,
)
from .onebot import OneBotError

logger = logging.getLogger(__name__)

# ``fetch(account_id, message_id)`` returns the message NapCat has under that ID.
RepliedMessageFetch = Callable[[str, str], Awaitable[RepliedMessage]]
# ``download(urls)`` stores pictures as local attachments and returns their paths.
ImageDownload = Callable[[list[str]], Awaitable[list[str]]]


async def with_replied_message(
    message: InboundMessage, fetch: RepliedMessageFetch
) -> tuple[InboundMessage, RepliedMessage | None]:
    """Asks NapCat once for the message ``message`` replies to, before routing.

    The CQ reply segment only carries the replied-to message's ID. Its sender
    goes into ``REPLY_TO_SENDER_ID_KEY``, which the host compares with the
    account's own QQ number to tell a group reply to the role; the replied
    message itself is handed back, kept out of the message until it is known
    to start a turn (``with_quote``). A failed query only costs the message
    its reply: it is logged and the message proceeds without one, so it does
    not count as a reply to the role. Failures are NapCat errors
    (``OneBotError``: the replied-to message expired or was recalled, the
    account has no live socket, or an in-flight reply was lost to a
    disconnect), a reply timeout, or the socket closing while sending.
    """
    replied_id = reply_message_id(message.content)
    if replied_id is None:
        return message, None
    account_id = str(message.metadata["account_id"])
    try:
        replied = await fetch(account_id, replied_id)
    except (OneBotError, TimeoutError, ConnectionClosed) as exc:
        logger.warning(
            "[qq] 账号 %s 被回复消息 %s 查询失败，消息不带回复对象: %s",
            account_id,
            replied_id,
            exc,
        )
        return message, None
    metadata = {**message.metadata, REPLY_TO_SENDER_ID_KEY: replied.sender_id}
    return replace(message, metadata=metadata), replied


async def with_quote(
    message: InboundMessage, replied: RepliedMessage, download: ImageDownload
) -> InboundMessage:
    """``message``, routed to a turn, with the text and pictures it quotes (#555).

    The quoted text loses its CQ codes: @ and a nested reply are dropped (a
    quote inside the quote is not followed), pictures are downloaded.
    """
    text, image_urls = extract_cq_images(
        strip_reply_segments(strip_at_segments(replied.raw_content))
    )
    return with_reply_quote(
        message,
        own_id=str(message.metadata["platform_account_id"]),
        text=text,
        sender_name=replied.sender_name,
        media=await download(image_urls),
        has_pictures=bool(image_urls),
    )
