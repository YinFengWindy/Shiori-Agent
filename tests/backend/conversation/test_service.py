"""The conversation service's group directory keeps role and thread boundaries."""

from pathlib import Path

from conversation.service import ConversationService, LegacySessionDescriptor
from session.manager import SessionManager


def test_group_directory_uses_recorded_types_and_current_role_ownership(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversations = ConversationService(manager)
    expected: set[str] = set()
    for role_id, chat_id, chat_type in (
        ("mira", "g", "group"),
        ("mira", "sg", "supergroup"),
        ("mira", "p", "private"),
        ("mira", "u", "unknown"),
        ("mira", "archived", "group"),
        ("nova", "other", "group"),
    ):
        thread = conversations.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"{role_id}:qq:{chat_id}",
                role_id=role_id,
                channel="qq",
                chat_id=chat_id,
            )
        )
        session = manager.get_or_create(f"role:{role_id}")
        session.add_message(
            "user",
            "hi",
            metadata={
                "thread_id": thread.id,
                "message_source": {"chat_type": chat_type},
            },
        )
        manager.save(session)
        if chat_id in {"g", "sg"}:
            expected.add(thread.id)
        if chat_id == "archived":
            _ = manager.conversation_store.archive_thread_and_release_legacy_session_key(
                thread.id
            )
    # A newly seen thread without a known chat type is not assumed to be a group.
    _ = conversations.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="qq:unclassified",
            role_id="mira",
            channel="qq",
            chat_id="unclassified",
        )
    )
    _ = conversations.ensure_desktop_thread("mira")

    assert {
        thread.id for thread in conversations.list_group_threads("mira")
    } == expected
