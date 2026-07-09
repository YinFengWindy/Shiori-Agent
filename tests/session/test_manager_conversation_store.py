from __future__ import annotations

from pathlib import Path

from session.manager import SessionManager


def test_session_manager_exposes_shared_conversation_store(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)

    assert manager.conversation_store.db_path == str(tmp_path / "sessions.db")
    assert manager.conversation_store.get_thread_by_legacy_session_key("role:mira") is None
