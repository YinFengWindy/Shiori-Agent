from __future__ import annotations

from pathlib import Path

from conversation.migrator import ConversationMigrator
from conversation.store import ConversationStore
from core.roles import RoleAggregateService, RoleStore
from session.manager import SessionManager
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


def test_conversation_migrator_merges_bound_channel_session_into_role_session(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "sessions.db"
    manager = SessionManager(tmp_path)
    legacy = manager.get_or_create("telegram:123")
    legacy.add_message("user", "hello")
    manager.save(legacy)

    migrator = ConversationMigrator(
        manager,
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
    role_session = manager.get_or_create("role:mira")
    assert [item["content"] for item in role_session.messages] == ["hello"]
    assert manager._store.get_session_meta("thread:mira:telegram:123") is None
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


def test_conversation_migrator_copies_network_history_to_role_session(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    legacy = manager.get_or_create("telegram:123")
    legacy.add_message("user", "old user")
    legacy.add_message("assistant", "old assistant")
    manager.save(legacy)
    migrator = ConversationMigrator(
        manager,
        binding_resolver=lambda channel, chat_id: "mira"
        if (channel, chat_id) == ("telegram", "123")
        else "",
    )

    first = migrator.migrate()
    runtime = manager.get_or_create("role:mira")
    second = migrator.migrate()

    assert first.migrated_session_keys == ["telegram:123"]
    assert [item["content"] for item in legacy.messages] == ["old user", "old assistant"]
    assert [item["content"] for item in runtime.messages] == [
        "old user",
        "old assistant",
    ]
    assert all(
        item["migration_source_session_key"] == "telegram:123"
        for item in runtime.messages
    )
    assert second.migrated_session_keys == []
    assert [item["content"] for item in runtime.messages] == [
        "old user",
        "old assistant",
    ]


def test_conversation_migrator_upgrades_unresolved_thread_into_role_session(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    legacy = manager.get_or_create("telegram:123")
    legacy.add_message("user", "old user")
    manager.save(legacy)

    missing = ConversationMigrator(manager)
    first = missing.migrate()
    resolved = ConversationMigrator(
        manager,
        binding_resolver=lambda channel, chat_id: "mira"
        if (channel, chat_id) == ("telegram", "123")
        else "",
    )
    second = resolved.migrate()
    thread = manager.conversation_store.get_thread_by_legacy_session_key("telegram:123")
    runtime = manager.get_or_create("role:mira")

    assert first.unresolved_session_keys == ["telegram:123"]
    assert second.migrated_session_keys == ["telegram:123"]
    assert thread is not None
    assert thread.thread_kind == "network"
    assert thread.role_id == "mira"
    assert [item["content"] for item in runtime.messages] == ["old user"]


def test_conversation_migrator_merges_multiple_channels_in_time_order(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    telegram = manager.get_or_create("telegram:123")
    telegram.add_message("user", "telegram")
    telegram.messages[-1]["timestamp"] = "2026-07-13T10:00:00+08:00"
    manager.save(telegram)
    qq = manager.get_or_create("qq:456")
    qq.add_message("user", "qq")
    qq.messages[-1]["timestamp"] = "2026-07-13T11:00:00+08:00"
    manager.save(qq)

    migrator = ConversationMigrator(
        manager,
        binding_resolver=lambda channel, chat_id: {
            ("telegram", "123"): "mira",
            ("qq", "456"): "mira",
        }.get((channel, chat_id), ""),
    )

    migrator.migrate()
    session = manager.get_or_create("role:mira")

    assert [item["content"] for item in session.messages] == ["telegram", "qq"]
    assert [item["thread_id"] for item in session.messages] == [
        "thread:mira:telegram:123",
        "thread:mira:qq:456",
    ]
    assert all(item["migration_source_message_id"] for item in session.messages)


def test_conversation_migrator_does_not_restore_messages_cleared_from_role_session(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    roles = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=manager,
    )
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.bindings.bind("telegram", "123", "mira")
    legacy = manager.get_or_create("telegram:123")
    legacy.add_message("user", "old")
    manager.save(legacy)
    roles.sessions.clear("mira")

    ConversationMigrator(
        manager,
        binding_resolver=roles.bindings.resolve_role_id,
    ).migrate()

    assert manager.get_or_create("role:mira").messages == []


def test_conversation_migrator_does_not_restore_messages_after_role_deletion(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    roles = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=manager,
    )
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.bindings.bind("telegram", "123", "mira")
    legacy = manager.get_or_create("telegram:123")
    legacy.add_message("user", "before deletion")
    manager.save(legacy)
    roles.delete_role("mira")
    roles.create_role(role_id="mira", name="Mira 2", system_prompt="test")
    roles.bindings.bind("telegram", "123", "mira")

    ConversationMigrator(
        manager,
        binding_resolver=roles.bindings.resolve_role_id,
    ).migrate()

    assert manager.get_or_create("role:mira").messages == []
