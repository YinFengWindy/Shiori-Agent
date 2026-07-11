from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from conversation.service import ConversationService, LegacySessionDescriptor

if TYPE_CHECKING:
    from session.manager import SessionManager


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
        session_manager: "SessionManager | str | Path",
        *,
        binding_resolver: Any | None = None,
    ) -> None:
        self._owns_session_manager = isinstance(session_manager, (str, Path))
        if self._owns_session_manager:
            from session.manager import SessionManager

            session_manager = SessionManager(Path(session_manager).parent)
        self._session_manager = session_manager
        self._service = ConversationService(
            session_manager=session_manager,
            binding_resolver=binding_resolver,
        )
        self._store = self._service._store

    def close(self) -> None:
        if self._owns_session_manager:
            self._session_manager._store.close()

    def migrate(self) -> ConversationMigrationSummary:
        summary = ConversationMigrationSummary()
        for row in self._store.list_legacy_sessions():
            session_key = str(row.get("key") or "").strip()
            if not session_key or session_key.startswith("thread:"):
                continue
            existing_thread = self._store.get_thread_by_legacy_session_key(session_key)
            if existing_thread is not None and existing_thread.thread_kind != "legacy/unresolved":
                self._sync_runtime_session(session_key, existing_thread, dict(row.get("metadata") or {}))
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
                self._sync_runtime_session(session_key, thread, dict(row.get("metadata") or {}))
                summary.migrated_session_keys.append(session_key)
            summary.migrated_thread_ids.append(thread.id)
        return summary

    def _sync_runtime_session(
        self,
        source_session_key: str,
        thread,
        metadata: dict[str, Any],
    ) -> None:
        if thread.thread_kind != "network":
            return
        target = self._session_manager.sync_thread_session_metadata(
            thread.id,
            role_id=thread.role_id,
            role_name=str(metadata.get("role_name") or thread.role_id),
            role_prompt=str(metadata.get("role_prompt") or ""),
            role_runtime_config=(
                dict(metadata["role_runtime_config"])
                if isinstance(metadata.get("role_runtime_config"), dict)
                else None
            ),
            thread_id=thread.id,
            context_channel=thread.channel,
            context_chat_id=thread.external_thread_id,
            transport_channel=thread.channel,
            transport_chat_id=thread.external_thread_id,
        )
        self._session_manager.copy_legacy_messages_to_thread_session(
            source_session_key,
            target,
            thread_id=thread.id,
        )

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
