from __future__ import annotations

from conversation.service import ConversationService
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import SessionManager


def test_session_presenter_serializes_formal_thread(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("user", "hello")
    manager.save(session)
    conversation = ConversationService(manager)
    thread = conversation.sync_session_messages_to_thread(
        session.key,
        role_id="mira",
        channel="desktop",
        chat_id="self",
    )

    payload = DesktopSessionPresenter(conversation).serialize(session)

    assert payload["thread"]["id"] == thread.id
    assert payload["messages"][0]["content"] == "hello"
