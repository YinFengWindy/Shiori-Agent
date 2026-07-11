from __future__ import annotations

from pathlib import Path

from bootstrap.conversation import migrate_workspace_conversations
from core.roles import RoleAggregateService, RoleStore
from session.manager import SessionManager


def test_workspace_conversation_migration_uses_role_channel_bindings(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    roles = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=manager,
    )
    role = roles.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    ).role
    _ = roles.bindings.bind("telegram", "42", role.id)
    legacy = manager.get_or_create("telegram:42")
    legacy.add_message("user", "hello")
    manager.save(legacy)

    summary = migrate_workspace_conversations(tmp_path, manager)

    assert summary.migrated_session_keys == ["role:mira", "telegram:42"]
    thread = manager.conversation_store.get_thread_by_legacy_session_key("telegram:42")
    assert thread is not None
    assert thread.role_id == role.id
