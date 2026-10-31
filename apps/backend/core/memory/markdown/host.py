"""``MARKDOWN_MEMORY``: roles' Markdown memory documents for plugins.

The port opens a role's ``MarkdownMemoryStore`` and keeps plugin-owned values
in the role's ``memory_init_state``. Nothing is cached: every call reads the
role store and the files again, so a reference stays valid across runtime
generations.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from conversation.context_scope import load_user_context_threads
from core.memory.markdown.recent_context_document import visible_recent_context
from core.memory.markdown_schema import DOCUMENT_DEFAULTS
from core.roles import RoleStore
from core.roles.memory_service import HOST_MEMORY_STATE_KEYS
from core.roles.self_seed_state import resolve_self_seed_state

from .runtime import MarkdownMemoryStore, resolve_markdown_store


class HostRoleMarkdownMemory:
    """One role's documents (``RoleMarkdownMemory``)."""

    def __init__(
        self,
        store: MarkdownMemoryStore,
        roles: RoleStore,
        role_id: str,
        workspace: Path,
    ):
        self._store = store
        self._roles = roles
        self._role_id = role_id
        self._workspace = workspace

    def read_long_term(self) -> str:
        return self._store.read_long_term()

    def read_self(self) -> str:
        return self._store.read_self()

    def write_self(self, content: str) -> None:
        self._store.write_self(content)

    def self_seed_pending(self) -> bool:
        role = self._roles.get_role(self._role_id)
        if role is None:
            return False
        seed = resolve_self_seed_state(role, self._store.read_self())
        return seed["status"] == "pending"

    def snapshot_pending(self) -> str:
        return self._store.snapshot_pending()

    def commit_long_term(self, content: str, *, history_entry: str) -> None:
        if self._store.read_long_term().strip():
            self._store.backup_long_term()
        self._store.write_long_term(content)
        if history_entry:
            self._store.append_history(history_entry)
        self._store.commit_pending_snapshot()

    def rollback_pending_snapshot(self) -> None:
        self._store.rollback_pending_snapshot()

    def read_recent_context(self) -> str:
        return visible_recent_context(
            self._store.read_recent_context(),
            load_user_context_threads(self._workspace, self._role_id),
        )

    def read_state(self) -> Mapping[str, object]:
        role = self._roles.get_role(self._role_id)
        if role is None:
            return {}
        return {
            key: value
            for key, value in role.memory_init_state.items()
            if key not in HOST_MEMORY_STATE_KEYS
        }

    def write_state(self, key: str, value: object) -> None:
        if key in HOST_MEMORY_STATE_KEYS:
            raise ValueError(f"memory state key {key!r} is reserved by the host")
        try:
            _ = json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"memory state value for {key!r} is not JSON serializable"
            ) from exc
        # Other flows (such as the first SELF generation) may rewrite the same
        # state while the caller awaited a model, so the role is read again
        # under the store lock and only this key changes.
        with self._roles.lock:
            role = self._roles.get_role(self._role_id)
            if role is None:
                return
            next_state: dict[str, object] = {**role.memory_init_state, key: value}
            if next_state != role.memory_init_state:
                _ = self._roles.update_role(self._role_id, memory_init_state=next_state)


class HostMarkdownMemory:
    """``MARKDOWN_MEMORY`` over the workspace's role directories."""

    def __init__(self, workspace: Path, roles: RoleStore) -> None:
        self._workspace = workspace
        self._roles = roles

    @property
    def default_self(self) -> str:
        return DOCUMENT_DEFAULTS["SELF.md"]

    def role(self, role_id: str) -> HostRoleMarkdownMemory | None:
        # Opening the store creates the role's memory directory, so a deleted
        # role is checked first instead of being recreated.
        if self._roles.get_role(role_id) is None:
            return None
        store = resolve_markdown_store(workspace=self._workspace, role_id=role_id)
        return HostRoleMarkdownMemory(store, self._roles, role_id, self._workspace)
