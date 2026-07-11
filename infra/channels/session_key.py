from __future__ import annotations

from bus.events import OutboundMessage


def resolve_outbound_session_key(
    message: OutboundMessage,
    *,
    default_channel: str,
) -> str:
    """Returns the runtime session key that owns an outbound channel response."""
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    override = str(metadata.get("session_key_override") or "").strip()
    if override:
        return override
    return f"{default_channel}:{message.chat_id}"
