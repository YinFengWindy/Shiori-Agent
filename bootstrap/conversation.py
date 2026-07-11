from __future__ import annotations

from pathlib import Path

from conversation.migrator import ConversationMigrationSummary, ConversationMigrator
from core.roles import RoleBindingService, RoleRepository, RoleStore
from session.manager import SessionManager


def migrate_workspace_conversations(
    workspace: Path,
    session_manager: SessionManager,
) -> ConversationMigrationSummary:
    """Migrates legacy session facts before channels and agent workers begin."""
    role_store = RoleStore(workspace)
    bindings = RoleBindingService(workspace, RoleRepository(role_store))
    migrator = ConversationMigrator(
        session_manager.db_path,
        binding_resolver=bindings.resolve_role_id,
    )
    try:
        return migrator.migrate()
    finally:
        migrator.close()
