"""Deleting a role's session takes its groups' listening data with it (#541)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from session.manager import SessionManager

_TABLES = (
    "listening_messages",
    "listening_groups",
    "listening_toggles",
    "listening_cursors",
)


def test_deleting_the_role_session_removes_only_that_roles_listening_rows(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    listening = manager.conversation_store.listening
    for index, group in enumerate(("thread:mira:qq:g1", "thread:yuki:qq:g1")):
        listening.switches.set_enabled(group, True, operator="user")
        _ = listening.hear(
            group,
            sender_id="555",
            content="在吗",
            source={},
            external_message_id=f"m{index}",
            timestamp=datetime(2026, 9, 30, 9, 0).astimezone(),
        )
        assert listening.cursors.advance(group, expected=0, to=1)
    manager.get_or_create("role:mira")

    manager.delete_role_session("mira")

    with closing(sqlite3.connect(tmp_path / "sessions.db")) as connection:
        left = {
            table: [
                row[0] for row in connection.execute(f"SELECT thread_id FROM {table}")
            ]
            for table in _TABLES
        }
    # 另一个角色的旁听数据原样保留。
    assert left == {table: ["thread:yuki:qq:g1"] for table in _TABLES}
    assert listening.recent("thread:mira:qq:g1") == []
