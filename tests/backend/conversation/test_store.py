from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

import conversation.store as conversation_store_module
from conversation.store import ConversationStore
from conversation.service import ConversationService, LegacySessionDescriptor
from session.manager import SessionManager
from session.store import SessionStore


def test_standalone_state_transaction_commits_and_rolls_back(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "transaction.db")
    try:
        with store.state_transaction():
            _ = store.upsert_thread_state(
                "thread", summary="原摘要", metadata={"count": 1}
            )
        before = store.get_thread_state("thread")
        with pytest.raises(OSError, match="write failed"):
            with store.state_transaction():
                _ = store.upsert_thread_state(
                    "thread", summary="新摘要", metadata={"count": 2}
                )
                _ = store.upsert_thread_state("new-thread", summary="应回滚")
                raise OSError("write failed")
        assert store.get_thread_state("thread") == before
        assert store.get_thread_state("new-thread") is None
    finally:
        store.close()


def test_standalone_state_upsert_commits_for_reopened_store(tmp_path: Path):
    path = tmp_path / "conversation.db"
    store = ConversationStore(path)
    store.upsert_thread_state("thread", summary="thread", metadata={"message_count": 1})
    store.upsert_contact_state(
        "contact", summary="contact", metadata={"last_message_at": "now"}
    )
    store.upsert_role_state(
        "role", summary="role", metadata={"last_thread_id": "thread"}
    )
    store.close()

    reopened = ConversationStore(path)
    try:
        assert reopened.get_thread_state("thread").metadata == {"message_count": 1}
        assert reopened.get_contact_state("contact").metadata == {
            "last_message_at": "now"
        }
        assert reopened.get_role_state("role").metadata == {"last_thread_id": "thread"}
    finally:
        reopened.close()


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


def test_conversation_service_resolves_thread_runtime_key(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    service = ConversationService(manager)
    thread = service.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:123",
            role_id="mira",
            channel="telegram",
            chat_id="123",
        )
    )

    resolved = service.get_thread_for_runtime(thread.id)

    assert resolved == thread


def test_conversation_service_archives_old_role_thread_on_channel_rebind(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    service = ConversationService(manager)
    first = service.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:123",
            role_id="mira",
            channel="telegram",
            chat_id="123",
        )
    )

    rebound = service.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:123",
            role_id="yuki",
            channel="telegram",
            chat_id="123",
        )
    )

    archived = manager.conversation_store.get_thread(first.id)
    mapped = manager.conversation_store.get_thread_by_legacy_session_key("telegram:123")

    assert archived is not None
    assert archived.archived is True
    assert archived.legacy_session_key == ""
    assert rebound.id == "thread:yuki:telegram:123"
    assert mapped == rebound


def test_last_user_message_at_reads_only_user_rows_of_one_thread(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    legacy.create_session(key="role:mira", metadata={"role_id": "mira"})
    rows = [
        ("user", "thread:mira:qq:10001", "2026-09-25T09:00:00+08:00"),
        ("user", "thread:mira:qq:10001", "2026-09-25T10:00:00+08:00"),
        # A later proactive reply is not the user speaking.
        ("assistant", "thread:mira:qq:10001", "2026-09-25T11:00:00+08:00"),
        ("user", "thread:mira:qq:gqq:7", "2026-09-25T12:00:00+08:00"),
    ]
    for seq, (role, thread_id, ts) in enumerate(rows):
        legacy.insert_message(
            "role:mira", role=role, content="x", ts=ts, seq=seq, thread_id=thread_id
        )
    legacy.close()

    store = ConversationStore(db_path)
    try:
        assert (
            store.last_user_message_at("thread:mira:qq:10001")
            == "2026-09-25T10:00:00+08:00"
        )
        assert store.last_user_message_at("thread:mira:telegram:42") is None
    finally:
        store.close()


def test_standalone_schema_failure_rolls_back_all_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "conversation.db"

    def fail_indexes(_connection: sqlite3.Connection) -> None:
        raise RuntimeError("injected index failure")

    monkeypatch.setattr(conversation_store_module, "_ensure_indexes", fail_indexes)

    with pytest.raises(RuntimeError, match="injected index failure"):
        ConversationStore(path)

    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_schema_helper_refuses_to_run_outside_a_transaction(tmp_path: Path) -> None:
    path = tmp_path / "conversation.db"
    with closing(sqlite3.connect(path)) as conn:
        with pytest.raises(RuntimeError, match="open transaction"):
            conversation_store_module.ensure_conversation_schema(conn)
        assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_thread_state_upsert_keeps_summary_and_merges_metadata(
    tmp_path: Path,
) -> None:
    store = ConversationStore(tmp_path / "conversation.db")
    try:
        store.upsert_thread_state(
            "thread", summary="群里在聊狗", metadata={"summary_updated_at": "t0"}
        )
        # 投影只写计数：不传 summary 时保留摘要，metadata 合并而不是覆盖。
        state = store.upsert_thread_state("thread", metadata={"message_count": 3})
    finally:
        store.close()

    assert state.summary == "群里在聊狗"
    assert state.metadata == {"summary_updated_at": "t0", "message_count": 3}


def test_list_summarized_thread_states_covers_the_roles_current_threads(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    service = ConversationService(manager)
    store = manager.conversation_store
    threads = {
        name: service.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"qq:{name}", role_id=role_id, channel="qq", chat_id=name
            )
        )
        for name, role_id in (
            ("current", "mira"),
            ("archived", "mira"),
            ("blank", "mira"),
            ("other", "luna"),
        )
    }
    for name, thread in threads.items():
        store.upsert_thread_state(thread.id, summary="" if name == "blank" else name)
    store.archive_thread_and_release_legacy_session_key(threads["archived"].id)

    states = store.list_summarized_thread_states("mira")

    assert [state.owner_id for state in states] == [threads["current"].id]


def test_thread_messages_since_compares_parsed_times_across_offsets(
    tmp_path: Path,
) -> None:
    """A row written in another offset is judged by its instant, not its text."""
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    for text, ts in (
        ("before", "2026-09-30T09:00:00+08:00"),
        # 11:30 +08:00, though its text sorts before the cutoff's.
        ("after", "2026-09-30T03:30:00+00:00"),
        ("no thread", "2026-09-30T12:00:00+08:00"),
    ):
        thread = "" if text == "no thread" else "thread:mira:qq:gqq:1"
        session.add_message("user", text, thread_id=thread)
        session.messages[-1]["timestamp"] = ts
    manager.save(session)

    rows = manager.conversation_store.thread_messages_since(
        "role:mira", datetime.fromisoformat("2026-09-30T10:00:00+08:00")
    )

    assert [row["content"] for row in rows] == ["after"]
