"""How the host projects admitted channel input onto a role's session.

The host's channel hub and the SDK's ``FakeChannelHub`` share these functions,
so plugin tests see exactly the metadata a routed message carries in the host.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shiori_sdk.messages import InboundMessage

from .message_source import REPLY_TO_SENDER_IS_USER_KEY, SENDER_IS_USER_KEY

# Flags only the host may assert; a plugin's own values are dropped on intake.
HOST_ASSERTED_KEYS = (SENDER_IS_USER_KEY, REPLY_TO_SENDER_IS_USER_KEY)


def plugin_metadata(message: InboundMessage) -> dict[str, Any]:
    """A copy of the message's metadata without the host-asserted flags."""
    metadata = dict(message.metadata or {})
    for key in HOST_ASSERTED_KEYS:
        metadata.pop(key, None)
    return metadata


def project_inbound(
    message: InboundMessage,
    metadata: Mapping[str, Any],
    *,
    role_id: str,
    thread_id: str,
    session_key: str,
    default_chat_type: str,
) -> InboundMessage:
    """``message`` addressed to ``role_id``'s session through thread ``thread_id``.

    ``metadata`` is the admitted metadata (see ``plugin_metadata``) plus any
    flags the host set; it is copied, not mutated. The platform message ID is
    normalized into ``external_message_id``, the transport origin is kept, and
    a missing ``chat_type`` takes the channel's ``default_chat_type``.
    """
    projected = dict(metadata)
    external_message_id = str(
        projected.get("external_message_id") or projected.get("message_id") or ""
    ).strip()
    if external_message_id:
        projected["external_message_id"] = external_message_id
    projected["role_id"] = role_id
    projected["thread_id"] = thread_id
    projected["session_key_override"] = session_key
    projected.setdefault("context_channel", message.channel)
    projected.setdefault("context_chat_id", message.chat_id)
    projected["transport_channel"] = message.channel
    projected["transport_chat_id"] = message.chat_id
    projected["sender_id"] = message.sender
    projected.setdefault("chat_type", default_chat_type)
    projected.setdefault("source", "role_account")
    return InboundMessage(
        channel=message.channel,
        sender=message.sender,
        chat_id=message.chat_id,
        content=message.content,
        timestamp=message.timestamp,
        media=list(message.media),
        metadata=projected,
    )
