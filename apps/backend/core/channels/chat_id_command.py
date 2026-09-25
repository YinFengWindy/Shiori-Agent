"""The ``/chatid`` reply every channel plugin gives, admission included.

Each channel plugin recognizes ``/chatid`` in its own inbound handling (next to
``/stop``, before hub admission) and hands it here; the command never reaches
the role.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from core.common.channel_chat_types import (
    ChatType,
    ChatTypeDeclaration,
    chat_id_command_reply,
)

from .hub import ChannelHub

logger = logging.getLogger(__name__)


async def answer_chat_id_command(
    hub: ChannelHub | None,
    *,
    channel: str,
    chat_id: str,
    chat_type: ChatType,
    sender_id: str,
    declarations: tuple[ChatTypeDeclaration, ...],
    send: Callable[[str], Awaitable[object]],
    sender_alias: str = "",
) -> None:
    """Replies with what the binding form asks for this chat, through ``send``.

    The one deliberate exception to "a rejected message has no side effect":
    ``/chatid`` is answered in a chat that is not bound yet, because it is how
    the user finds the number to bind. A sender a bound session blacklists
    still gets no reply and causes nothing. Without a hub (a channel driven
    outside the host) every sender is answered.
    """
    if hub is not None and hub.is_sender_blocked(
        channel=channel,
        chat_id=chat_id,
        sender_id=sender_id,
        sender_alias=sender_alias,
    ):
        logger.warning("[%s] 忽略黑名单成员的 /chatid chat_id=%s", channel, chat_id)
        return
    await send(chat_id_command_reply(chat_id, chat_type, declarations))
