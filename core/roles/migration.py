from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from infra.persistence.json_store import atomic_save_json, load_json
from memory2.store import MemoryStore2
from session.manager import SessionManager

from .services import RoleAggregateService, RoleChannelBinding

_MIGRATION_STATE_VERSION = 1


@dataclass
class RoleMigrationSummary:
    migrated_session_keys: list[str] = field(default_factory=list)
    migrated_memory_item_ids: list[str] = field(default_factory=list)
    migrated_bindings: list[str] = field(default_factory=list)
    unresolved_session_keys: list[str] = field(default_factory=list)
    unresolved_memory_item_ids: list[str] = field(default_factory=list)


class RoleLegacyMigrator:
    """角色化迁移器：只迁可确认归属的数据，重复执行幂等。"""

    def __init__(
        self,
        *,
        workspace: Path,
        roles: RoleAggregateService,
        session_manager: SessionManager,
        memory_store: MemoryStore2 | None = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._roles = roles
        self._session_manager = session_manager
        self._memory_store = memory_store
        self._state_path = self._workspace / "roles" / "migration_state.json"
        self._unresolved_path = self._workspace / "roles" / "migration_unresolved.json"

    def migrate(self) -> RoleMigrationSummary:
        state = self._load_state()
        summary = RoleMigrationSummary()

        for role in self._roles.repository.list_roles():
            _ = self._roles.open_role(role.id)

        summary.migrated_session_keys.extend(self._migrate_sessions(state, summary))
        summary.migrated_memory_item_ids.extend(self._migrate_memory_items(state, summary))
        summary.migrated_bindings.extend(self._migrate_bindings(state))

        self._save_state(state)
        self._save_unresolved(summary)
        return summary

    @staticmethod
    def _source_binding_from_session_key(session_key: str) -> tuple[str, str] | None:
        clean_key = str(session_key or "").strip()
        if not clean_key or clean_key.startswith("role:"):
            return None
        channel, sep, chat_id = clean_key.partition(":")
        if not sep:
            return None
        clean_channel = channel.strip()
        clean_chat_id = chat_id.strip()
        if not clean_channel or not clean_chat_id:
            return None
        return clean_channel, clean_chat_id

    @staticmethod
    def _message_signature(message: dict[str, Any]) -> str:
        payload = {
            "role": str(message.get("role") or ""),
            "content": str(message.get("content") or ""),
            "timestamp": str(message.get("timestamp") or ""),
            "tool_chain": message.get("tool_chain") or [],
            "proactive": bool(message.get("proactive")),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _migrate_sessions(
        self,
        state: dict[str, Any],
        summary: RoleMigrationSummary,
    ) -> list[str]:
        migrated: list[str] = []
        session_rows = self._session_manager._store.list_sessions()
        for row in session_rows:
            source_key = str(row.get("key") or "").strip()
            if not source_key or source_key.startswith("role:"):
                continue
            if source_key in set(state.get("migrated_session_keys") or []):
                continue
            meta = self._session_manager._store.get_session_meta(source_key) or {}
            metadata = meta.get("metadata") if isinstance(meta, dict) else {}
            role_id = str(metadata.get("role_id") or "").strip() if isinstance(metadata, dict) else ""
            if not role_id:
                summary.unresolved_session_keys.append(source_key)
                continue
            role = self._roles.repository.get_required(role_id)
            binding = self._source_binding_from_session_key(source_key)
            if binding is not None:
                channel, chat_id = binding
                binding_key = f"{channel}:{chat_id}"
                if binding_key not in set(state.get("migrated_bindings") or []):
                    self._roles.bindings.bind(channel, chat_id, role.id)
                    state.setdefault("migrated_bindings", []).append(binding_key)
                    summary.migrated_bindings.append(binding_key)
            target = self._roles.sessions.open_by_role(role)
            source_messages = self._session_manager._store.fetch_session_messages(source_key)
            existing_signatures = {
                self._message_signature(item)
                for item in self._session_manager._store.fetch_session_messages(target.key)
            }
            for message in source_messages:
                signature = self._message_signature(message)
                if signature in existing_signatures:
                    continue
                copied = dict(message)
                copied.pop("id", None)
                copied.pop("session_key", None)
                copied.pop("seq", None)
                target.messages.append(copied)
                existing_signatures.add(signature)
            self._session_manager.save(target)
            state.setdefault("migrated_session_keys", []).append(source_key)
            migrated.append(source_key)
        return migrated

    def _migrate_memory_items(
        self,
        state: dict[str, Any],
        summary: RoleMigrationSummary,
    ) -> list[str]:
        if self._memory_store is None:
            return []
        migrated: list[str] = []
        seen = set(state.get("migrated_memory_item_ids") or [])
        rows = self._memory_store.list_items_for_dashboard(page_size=10000)[0]
        for item in rows:
            item_id = str(item.get("id") or "").strip()
            if not item_id or item_id in seen:
                continue
            full = self._memory_store.get_item_for_dashboard(item_id, include_embedding=True)
            if full is None:
                continue
            extra = dict(full.get("extra_json") or {})
            role_id = str(extra.get("role_id") or "").strip()
            if not role_id:
                summary.unresolved_memory_item_ids.append(item_id)
                continue
            _ = self._roles.repository.get_required(role_id)
            state.setdefault("migrated_memory_item_ids", []).append(item_id)
            migrated.append(item_id)
        return migrated

    def _migrate_bindings(self, state: dict[str, Any]) -> list[str]:
        migrated: list[str] = []
        bindings = self._roles.bindings.list_bindings()
        seen = set(state.get("migrated_bindings") or [])
        for binding in bindings:
            key = f"{binding.channel}:{binding.chat_id}"
            if key in seen:
                continue
            state.setdefault("migrated_bindings", []).append(key)
            migrated.append(key)
        return migrated

    def _load_state(self) -> dict[str, Any]:
        payload = load_json(
            self._state_path,
            default={
                "version": _MIGRATION_STATE_VERSION,
                "migrated_session_keys": [],
                "migrated_memory_item_ids": [],
                "migrated_bindings": [],
            },
            domain="role_migration",
        )
        if not isinstance(payload, dict):
            return {
                "version": _MIGRATION_STATE_VERSION,
                "migrated_session_keys": [],
                "migrated_memory_item_ids": [],
                "migrated_bindings": [],
            }
        return payload

    def _save_state(self, state: dict[str, Any]) -> None:
        atomic_save_json(
            self._state_path,
            {
                "version": _MIGRATION_STATE_VERSION,
                "migrated_session_keys": list(state.get("migrated_session_keys") or []),
                "migrated_memory_item_ids": list(state.get("migrated_memory_item_ids") or []),
                "migrated_bindings": list(state.get("migrated_bindings") or []),
            },
            domain="role_migration",
        )

    def _save_unresolved(self, summary: RoleMigrationSummary) -> None:
        atomic_save_json(
            self._unresolved_path,
            {
                "unresolved_session_keys": list(summary.unresolved_session_keys),
                "unresolved_memory_item_ids": list(summary.unresolved_memory_item_ids),
            },
            domain="role_migration",
        )
