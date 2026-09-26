"""Select exact committed turn rows for desktop session update events."""

from typing import Any, cast

from bus.events_lifecycle import TurnCommitted
from session.manager import Session


def committed_turn_messages(
    session: Session, event: TurnCommitted | None
) -> list[dict[str, Any]] | None:
    """Selects a turn's rows by ID, including any intermediate tool pushes."""
    if event is None or "committed_message_ids" not in event.extra:
        return None
    message_ids = set(cast(list[str], event.extra["committed_message_ids"]))
    return [message for message in session.messages if message.get("id") in message_ids]
