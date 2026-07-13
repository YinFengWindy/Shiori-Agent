from __future__ import annotations

from bus.events import OutboundMessage


def resolve_outbound_session_key(
    message: OutboundMessage,
    *,
    default_channel: str,
) -> str:
    """Returns the role session key used for channel-local trace state."""
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    override = str(metadata.get("session_key_override") or "").strip()
    if override.startswith("role:"):
        return override
    role_id = str(metadata.get("role_id") or "").strip()
    if role_id:
        return f"role:{role_id}"
    return f"{default_channel}:{message.chat_id}"
