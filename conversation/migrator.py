from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conversation.service import ConversationService, LegacySessionDescriptor


@dataclass
class ConversationMigrationSummary:
    """Reports which legacy session keys were migrated into the new thread model."""

    migrated_session_keys: list[str] = field(default_factory=list)
    unresolved_session_keys: list[str] = field(default_factory=list)
    migrated_thread_ids: list[str] = field(default_factory=list)


class ConversationMigrator:
    """Migrates legacy session rows into `contacts + threads + message.thread_id`."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        binding_resolver: Any | None = None,
    ) -> None:
        self._service = ConversationService(
            session_manager=_MigratorSessionManagerProxy(db_path),
            binding_resolver=binding_resolver,
        )
        self._store = self._service._store

    def close(self) -> None:
        self._store.close()

    def migrate(self) -> ConversationMigrationSummary:
        summary = ConversationMigrationSummary()
        for row in self._store.list_legacy_sessions():
            session_key = str(row.get("key") or "").strip()
            if not session_key:
                continue
            existing_thread = self._store.get_thread_by_legacy_session_key(session_key)
            if (
                existing_thread is not None
                and self._store.count_unassigned_messages(session_key) == 0
            ):
                continue

            thread = self._service.sync_session_messages_to_thread(
                session_key,
                role_id=self._role_id_hint(session_key, dict(row.get("metadata") or {})),
                channel=self._channel(session_key),
                chat_id=self._chat_id(session_key),
                created_at=str(row.get("created_at") or ""),
                updated_at=str(row.get("updated_at") or ""),
                metadata=dict(row.get("metadata") or {}),
            )
            if thread.thread_kind == "legacy/unresolved":
                summary.unresolved_session_keys.append(session_key)
            else:
                summary.migrated_session_keys.append(session_key)
            summary.migrated_thread_ids.append(thread.id)
        return summary

    @staticmethod
    def _channel(session_key: str) -> str:
        channel, _, _ = str(session_key or "").partition(":")
        return channel.strip()

    @staticmethod
    def _chat_id(session_key: str) -> str:
        _, _, chat_id = str(session_key or "").partition(":")
        return chat_id.strip()

    @staticmethod
    def _role_id_hint(session_key: str, metadata: dict[str, Any]) -> str:
        if str(session_key or "").startswith("role:"):
            return str(session_key).removeprefix("role:").strip()
        return str(metadata.get("role_id") or "").strip()


class _MigratorSessionManagerProxy:
    """Small adapter so `ConversationService` can reuse its thread derivation helpers."""

    def __init__(self, db_path: str | Path) -> None:
        from conversation.store import ConversationStore

        self.db_path = str(db_path)
        self.conversation_store = ConversationStore(self.db_path)

    def role_session_key(self, role_id: str) -> str:
        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id 不能为空")
        return f"role:{clean_role_id}"
