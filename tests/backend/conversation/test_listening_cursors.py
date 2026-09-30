"""Each group's listening consolidation cursor moves on its own, only from where it was."""

from __future__ import annotations

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
