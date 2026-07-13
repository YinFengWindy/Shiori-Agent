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
        self._binding_resolver = binding_resolver
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
            metadata = dict(row.get("metadata") or {})
            role_id = self._role_id_hint(session_key)
            if not role_id and not session_key.startswith("role:"):
                role_id = self._resolve_bound_role(
                    self._channel(session_key),
                    self._chat_id(session_key),
                )
            existing_thread = self._store.get_thread_by_legacy_session_key(session_key)

            if session_key.startswith("role:"):
                thread = self._service.sync_session_messages_to_thread(
                    session_key,
                    role_id=role_id,
                    channel="desktop",
                    chat_id="self",
                    created_at=str(row.get("created_at") or ""),
                    updated_at=str(row.get("updated_at") or ""),
                    metadata=metadata,
                )
                if existing_thread is None or existing_thread.thread_kind == "legacy/unresolved":
                    summary.migrated_session_keys.append(session_key)
                    summary.migrated_thread_ids.append(thread.id)
                self._service.project_thread(thread)
                continue

            if not role_id:
                thread = self._service.sync_session_messages_to_thread(
                    session_key,
                    role_id="",
                    channel=self._channel(session_key),
                    chat_id=self._chat_id(session_key),
                    created_at=str(row.get("created_at") or ""),
                    updated_at=str(row.get("updated_at") or ""),
                    metadata=metadata,
                )
                if existing_thread is None or existing_thread.thread_kind == "legacy/unresolved":
                    summary.unresolved_session_keys.append(session_key)
                    summary.migrated_thread_ids.append(thread.id)
                continue

            thread = self._service.ensure_thread_for_session(
                LegacySessionDescriptor(
                    session_key=session_key,
                    role_id=role_id,
                    channel=self._channel(session_key),
                    chat_id=self._chat_id(session_key),
                    created_at=str(row.get("created_at") or ""),
                    updated_at=str(row.get("updated_at") or ""),
                    metadata=metadata,
                )
            )
            target = self._session_manager.get_or_create(
                self._session_manager.role_session_key(role_id)
            )
            self._sync_role_metadata(target, role_id, metadata)
            desktop_thread = self._service.ensure_desktop_thread(role_id)
            self._service.project_thread(desktop_thread)
            self._store.assign_legacy_messages_to_thread(session_key, thread.id)
            cleared_at = str(target.metadata.get("cleared_at") or "").strip()
            deleted_at = self._role_deleted_at(role_id)
            cutoff = max(cleared_at, deleted_at)
            self._session_manager.merge_legacy_messages_into_role_session(
                session_key,
                target,
                thread_id=thread.id,
                cleared_at=cutoff,
            )
            self._service.project_thread(thread)
            if thread.thread_kind == "legacy/unresolved":
                summary.unresolved_session_keys.append(session_key)
            else:
                if existing_thread is None or existing_thread.thread_kind == "legacy/unresolved":
                    summary.migrated_session_keys.append(session_key)
                    summary.migrated_thread_ids.append(thread.id)
        return summary

    def _sync_role_metadata(
        self,
        target,
        role_id: str,
        metadata: dict[str, Any],
    ) -> None:
        target.metadata.setdefault("role_id", role_id)
        for key in (
            "thread_id",
            "context_channel",
            "context_chat_id",
            "transport_channel",
            "transport_chat_id",
            "session_key_override",
        ):
            target.metadata.pop(key, None)
        for key in ("role_name", "role_prompt", "role_runtime_config"):
            value = metadata.get(key)
            if value and key not in target.metadata:
                target.metadata[key] = dict(value) if isinstance(value, dict) else value
        self._session_manager.save(target)

    def _role_deleted_at(self, role_id: str) -> str:
        state = self._store.get_role_state(role_id)
        if state is None:
            return ""
        return str(state.metadata.get("deleted_at") or "").strip()

    def _resolve_bound_role(self, channel: str, chat_id: str) -> str:
        if self._binding_resolver is None:
            return ""
        try:
            return str(self._binding_resolver(channel, chat_id) or "").strip()
        except KeyError:
            return ""

    @staticmethod
    def _channel(session_key: str) -> str:
        channel, _, _ = str(session_key or "").partition(":")
        return channel.strip()

    @staticmethod
    def _chat_id(session_key: str) -> str:
        _, _, chat_id = str(session_key or "").partition(":")
        return chat_id.strip()

    @staticmethod
    def _role_id_hint(session_key: str) -> str:
        if str(session_key or "").startswith("role:"):
            return str(session_key).removeprefix("role:").strip()
        return ""
