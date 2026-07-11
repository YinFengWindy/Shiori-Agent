from __future__ import annotations

from pathlib import Path

from conversation.migrator import ConversationMigrator
from conversation.store import ConversationStore
from session.store import SessionStore


def _seed_legacy_session(
    store: SessionStore,
    session_key: str,
    *,
    metadata: dict | None = None,
    content: str = "hello",
) -> None:
    store.create_session(key=session_key, metadata=metadata or {})
    store.insert_message(
        session_key,
        role="user",
        content=content,
        ts="2026-07-10T12:00:00+08:00",
        seq=0,
    )


def test_conversation_migrator_moves_role_session_to_desktop_thread(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    _seed_legacy_session(legacy, "role:mira")

    migrator = ConversationMigrator(db_path)
    summary = migrator.migrate()

    store = ConversationStore(db_path)
    thread = store.get_thread_by_legacy_session_key("role:mira")

    assert summary.migrated_session_keys == ["role:mira"]
    assert summary.unresolved_session_keys == []
    assert thread is not None
    assert thread.thread_kind == "desktop"
    assert thread.role_id == "mira"
    assert store.list_message_thread_ids("role:mira") == [thread.id]
    migrator.close()
    store.close()


def test_conversation_migrator_moves_bound_channel_session_to_network_thread(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    _seed_legacy_session(legacy, "telegram:123")

    migrator = ConversationMigrator(
        db_path,
        binding_resolver=lambda channel, chat_id: "mira"
        if (channel, chat_id) == ("telegram", "123")
        else "",
    )
    summary = migrator.migrate()

    store = ConversationStore(db_path)
    thread = store.get_thread_by_legacy_session_key("telegram:123")
    contacts = store.list_contacts()

    assert summary.migrated_session_keys == ["telegram:123"]
    assert summary.unresolved_session_keys == []
    assert thread is not None
    assert thread.thread_kind == "network"
    assert thread.channel == "telegram"
    assert thread.role_id == "mira"
    assert any(item.external_id == "123" and item.role_id == "mira" for item in contacts)
    assert store.list_message_thread_ids("telegram:123") == [thread.id]
    migrator.close()
    store.close()


def test_conversation_migrator_routes_unknown_session_to_legacy_unresolved(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    _seed_legacy_session(legacy, "qq:404")

    migrator = ConversationMigrator(db_path)
    summary = migrator.migrate()

    store = ConversationStore(db_path)
    thread = store.get_thread_by_legacy_session_key("qq:404")

    assert summary.migrated_session_keys == []
    assert summary.unresolved_session_keys == ["qq:404"]
    assert thread is not None
    assert thread.thread_kind == "legacy/unresolved"
    assert thread.role_id == "legacy/unresolved"
    assert store.list_message_thread_ids("qq:404") == [thread.id]
    migrator.close()
    store.close()


def test_conversation_migrator_handles_missing_binding_as_unresolved(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    _seed_legacy_session(legacy, "qq:404")

    def _missing_binding(_channel: str, _chat_id: str) -> str:
        raise KeyError("missing binding")

    migrator = ConversationMigrator(db_path, binding_resolver=_missing_binding)
    summary = migrator.migrate()

    assert summary.unresolved_session_keys == ["qq:404"]
    migrator.close()


def test_conversation_migrator_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    legacy = SessionStore(db_path)
    _seed_legacy_session(legacy, "role:mira")

    migrator = ConversationMigrator(db_path)
    first = migrator.migrate()
    second = migrator.migrate()

    assert first.migrated_session_keys == ["role:mira"]
    assert second.migrated_session_keys == []
    assert second.unresolved_session_keys == []
    migrator.close()
