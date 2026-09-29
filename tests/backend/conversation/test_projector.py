from __future__ import annotations

from pathlib import Path

from conversation.service import ConversationService, LegacySessionDescriptor
from session.manager import SessionManager


def test_projecting_new_messages_keeps_the_thread_summary(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    thread = ConversationService(manager).ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="qq:g1", role_id="mira", channel="qq", chat_id="g1"
        )
    )
    manager.conversation_store.upsert_thread_state(
        thread.id,
        summary="阿明在群里晒了新买的狗。",
        metadata={"summary_updated_at": "2026-09-30T10:00:00+08:00"},
    )

    session = manager.get_or_create("role:mira")
    session.add_message("user", "新消息", thread_id=thread.id)
    manager.save(session)

    state = manager.conversation_store.get_thread_state(thread.id)
    assert state is not None
    assert state.summary == "阿明在群里晒了新买的狗。"
    assert state.metadata["message_count"] == 1
