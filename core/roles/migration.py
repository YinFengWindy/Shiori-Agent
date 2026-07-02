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
_CONSOLIDATION_MARKER_PREFIX = "<!-- consolidation:"
_GROUP_MEMBER_ID_AMBIGUOUS = "__ambiguous__"


@dataclass
class RoleMigrationSummary:
    migrated_session_keys: list[str] = field(default_factory=list)
    migrated_memory_item_ids: list[str] = field(default_factory=list)
    migrated_bindings: list[str] = field(default_factory=list)
    unresolved_session_keys: list[str] = field(default_factory=list)
    unresolved_memory_item_ids: list[str] = field(default_factory=list)


@dataclass
class RoleGroupMemoryRepairSummary:
    role_id: str
    channel: str
    group_chat_id: str
    removed_history_blocks: int = 0
    removed_pending_blocks: int = 0
    removed_journal_blocks: int = 0
    cleared_recent_context: bool = False
    deleted_memory_item_ids: list[str] = field(default_factory=list)


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

    @staticmethod
    def _session_group_id(
        source_key: str,
        metadata: dict[str, Any] | None,
    ) -> str:
        if isinstance(metadata, dict):
            group_id = str(metadata.get("group_id") or "").strip()
            if group_id:
                return group_id
        binding = RoleLegacyMigrator._source_binding_from_session_key(source_key)
        if binding is None:
            return ""
        _channel, chat_id = binding
        if chat_id.startswith("gqq:"):
            return chat_id[len("gqq:") :].strip()
        return ""

    @staticmethod
    def _message_member_id(message: dict[str, Any]) -> str:
        metadata = message.get("metadata")
        msg_metadata = metadata if isinstance(metadata, dict) else {}
        for key in ("group_member_id", "member_id", "sender_id"):
            value = str(msg_metadata.get(key) or message.get(key) or "").strip()
            if value:
                return value
        return ""

    def _group_target_session(
        self,
        *,
        role_id: str,
        channel: str,
        group_id: str,
        member_id: str,
    ):
        target_key = self._roles.sessions.derive_group_member_session_key(
            role_id,
            group_id=group_id,
            member_id=member_id,
        )
        session = self._session_manager.get_or_create(target_key)
        session.metadata["role_id"] = role_id
        session.metadata["is_group_chat"] = True
        session.metadata["group_id"] = group_id
        session.metadata["group_member_id"] = member_id
        session.metadata["member_id"] = member_id
        session.metadata["group_context_key"] = self._roles.sessions.derive_group_context_key(
            channel=channel,
            group_id=group_id,
        )
        session.metadata.setdefault("context_channel", channel)
        source_chat_id = f"gqq:{group_id}" if channel == "qq" else group_id
        session.metadata.setdefault("context_chat_id", source_chat_id)
        session.metadata.setdefault("transport_channel", channel)
        session.metadata.setdefault("transport_chat_id", source_chat_id)
        return session

    def _migrate_group_session_messages(
        self,
        *,
        source_key: str,
        role_id: str,
        group_id: str,
        source_messages: list[dict[str, Any]],
        summary: RoleMigrationSummary,
    ) -> bool:
        binding = self._source_binding_from_session_key(source_key)
        if binding is None:
            summary.unresolved_session_keys.append(source_key)
            return False
        channel, _chat_id = binding
        pending_by_member: dict[str, list[dict[str, Any]]] = {}
        current_member_id = ""
        for message in source_messages:
            role = str(message.get("role") or "").strip().lower()
            if role == "user":
                current_member_id = self._message_member_id(message)
                if not current_member_id:
                    summary.unresolved_session_keys.append(source_key)
                    return False
            elif role == "assistant":
                if not current_member_id:
                    summary.unresolved_session_keys.append(source_key)
                    return False
            else:
                continue
            copied = dict(message)
            copied.pop("id", None)
            copied.pop("session_key", None)
            copied.pop("seq", None)
            pending_by_member.setdefault(current_member_id, []).append(copied)

        for member_id, messages in pending_by_member.items():
            target = self._group_target_session(
                role_id=role_id,
                channel=channel,
                group_id=group_id,
                member_id=member_id,
            )
            existing_signatures = {
                self._message_signature(item)
                for item in self._session_manager._store.fetch_session_messages(target.key)
            }
            for copied in messages:
                signature = self._message_signature(copied)
                if signature in existing_signatures:
                    continue
                target.messages.append(copied)
                existing_signatures.add(signature)
            self._session_manager.save(target)
        return True

    @staticmethod
    def _is_group_relationship_memory(extra: dict[str, Any]) -> bool:
        if str(extra.get("memory_domain") or "").strip() != "relationship":
            return False
        scope_chat_id = str(extra.get("scope_chat_id") or "").strip()
        if scope_chat_id.startswith("gqq:"):
            return True
        return bool(str(extra.get("group_id") or "").strip())

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
            source_messages = self._session_manager._store.fetch_session_messages(source_key)
            group_id = self._session_group_id(source_key, metadata if isinstance(metadata, dict) else None)
            if group_id:
                migrated_group = self._migrate_group_session_messages(
                    source_key=source_key,
                    role_id=role.id,
                    group_id=group_id,
                    source_messages=source_messages,
                    summary=summary,
                )
                if not migrated_group:
                    continue
            else:
                target = self._roles.sessions.open_by_role(role)
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
            if self._is_group_relationship_memory(extra) and not str(
                extra.get("group_member_id") or ""
            ).strip():
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


class RoleGroupMemoryRepairer:
    """清理历史遗留的群聊污染角色根记忆。"""

    def __init__(
        self,
        *,
        workspace: Path,
        memory_store: MemoryStore2 | None = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._memory_store = memory_store

    def repair(
        self,
        *,
        role_id: str,
        channel: str,
        group_chat_id: str,
    ) -> RoleGroupMemoryRepairSummary:
        clean_role_id = str(role_id or "").strip()
        clean_channel = str(channel or "").strip()
        clean_group_chat_id = str(group_chat_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id 不能为空")
        if not clean_channel:
            raise ValueError("channel 不能为空")
        if not clean_group_chat_id:
            raise ValueError("group_chat_id 不能为空")

        summary = RoleGroupMemoryRepairSummary(
            role_id=clean_role_id,
            channel=clean_channel,
            group_chat_id=clean_group_chat_id,
        )
        group_source_prefix = (
            f"role:{clean_role_id}:group:{clean_group_chat_id}:member:"
        )
        memory_root = self._workspace / "roles" / clean_role_id / "memory"

        summary.removed_history_blocks = self._repair_markdown_file(
            memory_root / "HISTORY.md",
            group_source_prefix=group_source_prefix,
        )
        summary.removed_pending_blocks = self._repair_markdown_file(
            memory_root / "PENDING.md",
            group_source_prefix=group_source_prefix,
        )

        journal_dir = memory_root / "journal"
        if journal_dir.exists():
            for journal_file in sorted(journal_dir.glob("*.md")):
                summary.removed_journal_blocks += self._repair_markdown_file(
                    journal_file,
                    group_source_prefix=group_source_prefix,
                )

        if (
            summary.removed_history_blocks
            or summary.removed_pending_blocks
            or summary.removed_journal_blocks
        ):
            recent_context_path = memory_root / "RECENT_CONTEXT.md"
            if recent_context_path.exists():
                recent_context_path.write_text("", encoding="utf-8")
                summary.cleared_recent_context = True

        if self._memory_store is not None:
            summary.deleted_memory_item_ids.extend(
                self._repair_memory2_items(
                    role_id=clean_role_id,
                    channel=clean_channel,
                    group_chat_id=clean_group_chat_id,
                    group_source_prefix=group_source_prefix,
                )
            )
        return summary

    def _repair_markdown_file(
        self,
        path: Path,
        *,
        group_source_prefix: str,
    ) -> int:
        if not path.exists():
            return 0
        original = path.read_text(encoding="utf-8")
        cleaned, removed_blocks = _strip_group_consolidation_blocks(
            original,
            group_source_prefix=group_source_prefix,
        )
        if removed_blocks:
            path.write_text(cleaned, encoding="utf-8")
        return removed_blocks

    def _repair_memory2_items(
        self,
        *,
        role_id: str,
        channel: str,
        group_chat_id: str,
        group_source_prefix: str,
    ) -> list[str]:
        memory_store = self._memory_store
        if memory_store is None:
            return []

        scope_chat_ids = {group_chat_id}
        if channel == "qq":
            scope_chat_ids.add(f"gqq:{group_chat_id}")

        deleted_ids: list[str] = []
        page = 1
        page_size = 500
        while True:
            items, total = memory_store.list_items_for_dashboard(
                role_id=role_id,
                page=page,
                page_size=page_size,
                sort_by="created_at",
                sort_order="asc",
            )
            if not items:
                break
            for item in items:
                source_ref = str(item.get("source_ref") or "").strip()
                if group_source_prefix not in source_ref:
                    continue
                item_id = str(item.get("id") or "").strip()
                if not item_id:
                    continue
                full_item = memory_store.get_item_for_dashboard(item_id)
                if full_item is None:
                    continue
                if not _should_delete_group_memory_item(
                    full_item,
                    channel=channel,
                    scope_chat_ids=scope_chat_ids,
                ):
                    continue
                deleted_ids.append(item_id)
            if page * page_size >= total:
                break
            page += 1

        if deleted_ids:
            _ = memory_store.delete_items_batch(deleted_ids)
        return deleted_ids


def _strip_group_consolidation_blocks(
    text: str,
    *,
    group_source_prefix: str,
) -> tuple[str, int]:
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    removed_blocks = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith(_CONSOLIDATION_MARKER_PREFIX) and group_source_prefix in line:
            removed_blocks += 1
            index += 1
            while index < len(lines) and not lines[index].startswith(
                _CONSOLIDATION_MARKER_PREFIX
            ):
                index += 1
            continue
        kept.append(line)
        index += 1
    return "".join(kept), removed_blocks


def _should_delete_group_memory_item(
    item: dict[str, Any],
    *,
    channel: str,
    scope_chat_ids: set[str],
) -> bool:
    memory_type = str(item.get("memory_type") or "").strip()
    extra = item.get("extra_json")
    extra_json = extra if isinstance(extra, dict) else {}
    group_member_id = str(extra_json.get("group_member_id") or "").strip()
    scope_channel = str(extra_json.get("scope_channel") or "").strip()
    scope_chat_id = str(extra_json.get("scope_chat_id") or "").strip()

    if not memory_type:
        return True
    if not scope_channel or not scope_chat_id:
        return True
    if scope_channel != channel:
        return True
    if scope_chat_id not in scope_chat_ids:
        return True
    if group_member_id in {"", _GROUP_MEMBER_ID_AMBIGUOUS}:
        return True
    return False
