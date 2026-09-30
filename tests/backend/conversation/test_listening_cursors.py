"""Each group's listening consolidation cursor moves on its own, only from where it was."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from conversation.store import ConversationStore

_GROUP = "thread:mira:qq:g1"
_OTHER = "thread:mira:qq:g2"


def test_a_stale_advance_changes_nothing_and_groups_are_independent(
    tmp_path: Path,
) -> None:
    cursors = ConversationStore(tmp_path / "sessions.db").listening.cursors

    assert cursors.advance(_GROUP, expected=0, to=50)
    # Another consolidation prepared against the old cursor loses.
    assert not cursors.advance(_GROUP, expected=0, to=30)

    assert cursors.get(_GROUP) == 50
    assert cursors.get(_OTHER) == 0


def test_pending_groups_lists_unconsolidated_records_even_after_turning_off(
    tmp_path: Path,
) -> None:
    listening = ConversationStore(tmp_path / "sessions.db").listening
    for index, group in enumerate((_GROUP, _OTHER)):
        listening.switches.set_enabled(group, True, operator="user")
        _ = listening.hear(
            group,
            sender_id="555",
            content="在吗",
            source={},
            external_message_id=f"m{index}",
            timestamp=datetime(2026, 9, 30, 9, 0).astimezone(),
        )
    listening.switches.set_enabled(_OTHER, False, operator="user")
    assert listening.cursors.advance(_GROUP, expected=0, to=1)

    assert listening.cursors.pending_groups() == [_OTHER]
