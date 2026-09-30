"""When a group's unconsolidated listening records are due, and which of them."""

from __future__ import annotations

from datetime import datetime, timedelta

from conversation.listening_store import ListeningMessage
from core.memory.markdown.listening_window import (
    LISTENING_BATCH_SIZE,
    select_listening_batch,
)

_DAY = datetime(2026, 9, 29, 20, 0).astimezone()


def _records(count: int, start: datetime, first_seq: int = 1) -> list[ListeningMessage]:
    return [
        ListeningMessage(
            id=f"listen:{first_seq + index}",
            thread_id="thread:mira:qq:g1",
            seq=first_seq + index,
            sender_id="555",
            content=f"第{first_seq + index}条",
            source={},
            external_message_id="",
            timestamp=(start + timedelta(minutes=index)).isoformat(),
        )
        for index in range(count)
    ]


def test_a_full_batch_is_due_and_a_short_one_of_the_same_day_is_not() -> None:
    assert select_listening_batch(_records(LISTENING_BATCH_SIZE - 1, _DAY)) == []

    full = _records(LISTENING_BATCH_SIZE, _DAY)
    assert select_listening_batch(full) == full


def test_crossing_a_day_consolidates_the_earlier_days_only() -> None:
    yesterday = _records(3, _DAY)
    today = _records(1, _DAY + timedelta(days=1), first_seq=4)

    assert select_listening_batch([*yesterday, *today]) == yesterday
