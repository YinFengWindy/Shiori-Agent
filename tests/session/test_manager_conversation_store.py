from __future__ import annotations

from pathlib import Path

from session.manager import SessionManager


def test_session_manager_exposes_shared_conversation_store(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)

    assert manager.conversation_store.db_path == str(tmp_path / "sessions.db")
    assert manager.conversation_store.get_thread_by_legacy_session_key("role:mira") is None


def test_full_message_sync_preserves_conversation_columns(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("thread:mira:telegram:123")
    session.add_message(
        "assistant",
        "first reply",
        thread_id="thread:mira:telegram:123",
        external_message_id="tg-1",
        delivery_status="sent",
    )
    manager.save(session)

    session.messages[-1]["content"] = "edited reply"
    manager.save(session)

    persisted = manager._store.fetch_session_messages(session.key)
    assert persisted[0]["thread_id"] == "thread:mira:telegram:123"
    assert persisted[0]["external_message_id"] == "tg-1"
    assert persisted[0]["delivery_status"] == "sent"
