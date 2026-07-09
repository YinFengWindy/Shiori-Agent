from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conversation.store import ConversationStore

_LEGACY_UNRESOLVED_ROLE_ID = "legacy/unresolved"


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
        self._store = ConversationStore(db_path)
        self._binding_resolver = binding_resolver

    def close(self) -> None:
        self._store.close()

    def migrate(self) -> ConversationMigrationSummary:
        summary = ConversationMigrationSummary()
        for row in self._store.list_legacy_sessions():
            session_key = str(row.get("key") or "").strip()
            if not session_key:
                continue
            existing_thread = self._store.get_thread_by_legacy_session_key(session_key)
            if existing_thread is not None and self._store.count_unassigned_messages(session_key) == 0:
                continue

            thread = self._migrate_session(row)
            if thread.thread_kind == "legacy/unresolved":
                summary.unresolved_session_keys.append(session_key)
            else:
                summary.migrated_session_keys.append(session_key)
            summary.migrated_thread_ids.append(thread.id)
        return summary

    def _migrate_session(self, row: dict[str, Any]):
        session_key = str(row.get("key") or "").strip()
        metadata = dict(row.get("metadata") or {})
        created_at = str(row.get("created_at") or "")
        updated_at = str(row.get("updated_at") or "")

        if session_key.startswith("role:"):
            role_id = session_key.removeprefix("role:").strip()
            thread = self._build_desktop_thread(
                role_id,
                session_key=session_key,
                created_at=created_at,
                updated_at=updated_at,
            )
            self._store.assign_legacy_messages_to_thread(session_key, thread.id)
            return thread

        channel, sep, chat_id = session_key.partition(":")
        if sep:
            resolved_role_id = self._resolve_role_id(
                channel.strip(),
                chat_id.strip(),
                metadata,
            )
            if resolved_role_id:
                thread = self._build_network_thread(
                    resolved_role_id,
                    channel=channel.strip(),
                    chat_id=chat_id.strip(),
                    session_key=session_key,
                    created_at=created_at,
                    updated_at=updated_at,
                )
                self._store.assign_legacy_messages_to_thread(session_key, thread.id)
                return thread

        thread = self._build_unresolved_thread(
            session_key=session_key,
            channel=channel.strip() if sep else "unknown",
            external_id=chat_id.strip() if sep else session_key,
            created_at=created_at,
            updated_at=updated_at,
        )
        self._store.assign_legacy_messages_to_thread(session_key, thread.id)
        return thread

    def _resolve_role_id(
        self,
        channel: str,
        chat_id: str,
        metadata: dict[str, Any],
    ) -> str:
        if self._binding_resolver is not None:
            resolved = str(self._binding_resolver(channel, chat_id) or "").strip()
            if resolved:
                return resolved
        return str(metadata.get("role_id") or "").strip()

    def _build_desktop_thread(
        self,
        role_id: str,
        *,
        session_key: str,
        created_at: str,
        updated_at: str,
    ):
        contact = self._store.upsert_contact(
            contact_id=f"contact:{role_id}:desktop:self",
            role_id=role_id,
            kind="self_user",
            channel="desktop",
            external_id="self",
            display_name="你",
            metadata={"scope": "desktop"},
        )
        return self._store.upsert_thread(
            thread_id=f"thread:{role_id}:desktop",
            role_id=role_id,
            contact_id=contact.id,
            channel="desktop",
            thread_kind="desktop",
            external_thread_id="desktop",
            legacy_session_key=session_key,
            metadata={
                "migrated_from_session_key": session_key,
                "source_created_at": created_at,
                "source_updated_at": updated_at,
            },
        )

    def _build_network_thread(
        self,
        role_id: str,
        *,
        channel: str,
        chat_id: str,
        session_key: str,
        created_at: str,
        updated_at: str,
    ):
        contact = self._store.upsert_contact(
            contact_id=f"contact:{role_id}:{channel}:{chat_id}",
            role_id=role_id,
            kind="channel_peer",
            channel=channel,
            external_id=chat_id,
            display_name=chat_id,
            metadata={"scope": "network"},
        )
        return self._store.upsert_thread(
            thread_id=f"thread:{role_id}:{channel}:{chat_id}",
            role_id=role_id,
            contact_id=contact.id,
            channel=channel,
            thread_kind="network",
            external_thread_id=chat_id,
            legacy_session_key=session_key,
            metadata={
                "migrated_from_session_key": session_key,
                "source_created_at": created_at,
                "source_updated_at": updated_at,
            },
        )

    def _build_unresolved_thread(
        self,
        *,
        session_key: str,
        channel: str,
        external_id: str,
        created_at: str,
        updated_at: str,
    ):
        contact = self._store.upsert_contact(
            contact_id=f"contact:{_LEGACY_UNRESOLVED_ROLE_ID}:{channel}:unresolved",
            role_id=_LEGACY_UNRESOLVED_ROLE_ID,
            kind="legacy_unresolved",
            channel=channel or "unknown",
            external_id=external_id or session_key,
            display_name=session_key,
            metadata={"scope": "legacy/unresolved"},
        )
        safe_session_key = session_key.replace("/", "_")
        return self._store.upsert_thread(
            thread_id=f"thread:{_LEGACY_UNRESOLVED_ROLE_ID}:{safe_session_key}",
            role_id=_LEGACY_UNRESOLVED_ROLE_ID,
            contact_id=contact.id,
            channel=channel or "unknown",
            thread_kind="legacy/unresolved",
            external_thread_id=external_id or session_key,
            legacy_session_key=session_key,
            metadata={
                "migrated_from_session_key": session_key,
                "source_created_at": created_at,
                "source_updated_at": updated_at,
            },
        )
