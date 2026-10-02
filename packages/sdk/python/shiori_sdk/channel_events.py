"""Public turn events consumed by streaming transports."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TurnStarted:
    """The stable transport identity and content of a newly accepted turn."""

    session_key: str
    channel: str
    chat_id: str
    content: str
    timestamp: datetime
    role_id: str = ""
    # Stable inbound transport identity, retained even if a newer message arrives.
    external_message_id: str = ""


@dataclass(frozen=True)
class StreamDeltaReady:
    """One content or thinking delta for the identified turn's live preview."""

    session_key: str
    channel: str
    chat_id: str
    content_delta: str = ""
    thinking_delta: str = ""
    role_id: str = ""
    external_message_id: str = ""


@dataclass(frozen=True)
class TurnCancelled:
    """Signals that an originating turn will not produce more stream deltas."""

    session_key: str
    channel: str
    chat_id: str
    external_message_id: str = ""
