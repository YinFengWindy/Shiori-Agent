from __future__ import annotations

import sqlite3
from pathlib import Path

from conversation.store import ConversationStore
from session.store import SessionStore


def test_conversation_store_ensures_schema_and_message_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    store = ConversationStore(db_path)
    store.close()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        message_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
    finally:
        conn.close()

    assert {
        "sessions",
        "messages",
        "contacts",
        "threads",
        "thread_state",
        "contact_state",
        "role_state",
    }.issubset(tables)
    assert {
        "thread_id",
        "sender_role",
        "media",
        "external_message_id",
        "delivery_status",
    }.issubset(message_columns)


def test_conversation_store_assigns_legacy_messages_to_thread(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    legacy.create_session(key="role:mira", metadata={})
    legacy.insert_message(
        "role:mira",
        role="user",
        content="hello",
        ts="2026-07-10T12:00:00+08:00",
        seq=0,
    )

    store = ConversationStore(db_path)
    contact = store.upsert_contact(
        contact_id="contact:mira:desktop:self",
        role_id="mira",
        kind="self_user",
        channel="desktop",
        external_id="self",
        display_name="你",
        metadata={},
    )
    thread = store.upsert_thread(
        thread_id="thread:mira:desktop",
        role_id="mira",
        contact_id=contact.id,
        channel="desktop",
        thread_kind="desktop",
        external_thread_id="desktop",
        legacy_session_key="role:mira",
        metadata={},
    )

    updated = store.assign_legacy_messages_to_thread("role:mira", thread.id)

    assert updated == 1
    assert store.list_message_thread_ids("role:mira") == [thread.id]
    store.close()


def test_session_store_message_roundtrip_preserves_conversation_fields(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    legacy.create_session(key="telegram:123", metadata={"role_id": "mira"})
    legacy.insert_message(
        "telegram:123",
        role="user",
        content="hello",
        ts="2026-07-10T12:00:00+08:00",
        seq=0,
        thread_id="thread:mira:telegram:123",
        sender_role="user",
        media=["D:\\files\\scene.png"],
        external_message_id="telegram-msg-1",
        delivery_status="received",
    )

    messages = legacy.fetch_session_messages("telegram:123")

    assert messages[0]["thread_id"] == "thread:mira:telegram:123"
    assert messages[0]["sender_role"] == "user"
    assert messages[0]["media"] == ["D:\\files\\scene.png"]
    assert messages[0]["external_message_id"] == "telegram-msg-1"
    assert messages[0]["delivery_status"] == "received"
