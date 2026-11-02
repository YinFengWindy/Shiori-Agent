from __future__ import annotations

from shiori_sdk.messages import OutboundMessage
from shiori_sdk.session_keys import ROLE_SESSION_PREFIX, role_session_key


def resolve_outbound_session_key(
    message: OutboundMessage,
    *,
    default_channel: str,
) -> str:
    """Returns the role session key used for channel-local trace state."""
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    override = str(metadata.get("session_key_override") or "").strip()
    if override.startswith(ROLE_SESSION_PREFIX):
        return override
    role_id = str(metadata.get("role_id") or "").strip()
    if role_id:
        return role_session_key(role_id)
    return f"{default_channel}:{message.chat_id}"
