"""Atomic deletion contracts for session message persistence."""

from pathlib import Path

import pytest

from session.store import SessionStore


@pytest.mark.parametrize("invalid_id", ["missing", "other:0", "session:0"])
def test_delete_rejects_partial_foreign_or_duplicate_ids_without_cursor_change(
    tmp_path: Path, invalid_id: str
):
    store = SessionStore(tmp_path / "sessions.db")
    try:
        for key in ["session", "other"]:
            store.create_session(key=key, metadata={})
            store.insert_message(
                key, role="user", content="question", ts="2026-09-11", seq=0
            )
        before = store.get_session_meta("session")
        with pytest.raises(ValueError, match="撤销消息已发生变化"):
            store.delete_session_messages_and_update_cursor(
                "session", ids=["session:0", invalid_id], last_consolidated=42
            )
        assert store.get_message("session:0") is not None
        assert store.get_message("other:0") is not None
        assert store.get_session_meta("session") == before
    finally:
        store.close()


def test_update_message_delivery_writes_only_the_named_row(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    try:
        store.create_session(key="session", metadata={})
        store.insert_message(
            "session",
            role="assistant",
            content="older",
            ts="2026-09-17",
            seq=0,
            thread_id="thread-1",
        )
        store.insert_message(
            "session",
            role="assistant",
            content="target",
            ts="2026-09-17",
            seq=1,
            thread_id="thread-1",
        )

        updated = store.update_message_delivery(
            "session:1",
            session_key="session",
            thread_id="thread-1",
            delivery_status="sent",
            external_message_id="ext-1",
        )

        assert updated is not None
        assert updated["id"] == "session:1"
        assert updated["delivery_status"] == "sent"
        assert updated["external_message_id"] == "ext-1"
        older = store.get_message("session:0")
        assert older is not None
        assert older.get("delivery_status") is None
        assert older.get("external_message_id") is None
    finally:
        store.close()


def test_update_message_delivery_refuses_when_message_missing(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    try:
        store.create_session(key="session", metadata={})
        assert (
            store.update_message_delivery(
                "",
                session_key="session",
                thread_id="thread-1",
                delivery_status="sent",
            )
            is None
        )
        assert (
            store.update_message_delivery(
                "session:missing",
                session_key="session",
                thread_id="thread-1",
                delivery_status="sent",
            )
            is None
        )
    finally:
        store.close()


def test_update_message_delivery_refuses_cross_thread_and_cross_session_writes(
    tmp_path: Path,
):
    store = SessionStore(tmp_path / "sessions.db")
    try:
        store.create_session(key="session", metadata={})
        store.insert_message(
            "session",
            role="assistant",
            content="reply",
            ts="2026-09-17",
            seq=0,
            thread_id="thread-1",
        )

        # Correct session_key, wrong thread_id: rejected.
        assert (
            store.update_message_delivery(
                "session:0",
                session_key="session",
                thread_id="thread-other",
                delivery_status="sent",
            )
            is None
        )
        # Wrong session_key, correct thread_id: rejected.
        assert (
            store.update_message_delivery(
                "session:0",
                session_key="other-session",
                thread_id="thread-1",
                delivery_status="sent",
            )
            is None
        )
        # Correct session_key, but an empty thread_id (the caller failing to
        # supply one) must not silently skip the thread comparison: the
        # message's own thread_id ("thread-1") does not equal "", so this is
        # still a mismatch and must be rejected rather than falling through
        # to a write. This pins the unconditional comparison behavior added
        # for #305 (session_key/thread_id used to default to "" and skip
        # their check entirely when omitted).
        assert (
            store.update_message_delivery(
                "session:0",
                session_key="session",
                thread_id="",
                delivery_status="sent",
            )
            is None
        )
        untouched = store.get_message("session:0")
        assert untouched is not None
        assert untouched.get("delivery_status") is None
    finally:
        store.close()


def test_delete_rolls_back_when_database_skips_one_selected_row(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions.db")
    try:
        store.create_session(key="session", metadata={})
        for seq in range(2):
            store.insert_message(
                "session", role="user", content="question", ts="2026-09-11", seq=seq
            )
        store._conn.execute(
            "CREATE TRIGGER keep_message BEFORE DELETE ON messages WHEN old.id = 'session:1' BEGIN SELECT RAISE(IGNORE); END"
        )
        store._conn.commit()
        before = store.get_session_meta("session")

        with pytest.raises(ValueError, match="撤销消息未完整删除"):
            store.delete_session_messages_and_update_cursor(
                "session", ids=["session:0", "session:1"], last_consolidated=42
            )

        assert [
            message["id"] for message in store.fetch_session_messages("session")
        ] == ["session:0", "session:1"]
        assert store.get_session_meta("session") == before
    finally:
        store.close()
