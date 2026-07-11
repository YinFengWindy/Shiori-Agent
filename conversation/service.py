from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from conversation.models import ThreadRecord
from conversation.projector import ConversationStateProjector
from conversation.store import ConversationStore

if TYPE_CHECKING:
    from session.manager import SessionManager

_LEGACY_UNRESOLVED_ROLE_ID = "legacy/unresolved"


@dataclass(frozen=True)
class LegacySessionDescriptor:
    """Describes a legacy `session_key` that should resolve to a formal thread."""

    session_key: str
    role_id: str
    channel: str
    chat_id: str
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] | None = None


class ConversationService:
    """Owns the mapping between legacy session keys and formal conversation threads."""

    def __init__(
        self,
        session_manager: "SessionManager",
        *,
        binding_resolver: Callable[[str, str], str] | None = None,
    ) -> None:
        self._session_manager = session_manager
        shared_store = getattr(session_manager, "conversation_store", None)
        if shared_store is not None:
            self._store = shared_store
        else:
            db_path = getattr(session_manager, "db_path", None)
            if db_path is None:
                workspace = getattr(session_manager, "workspace", None)
                if workspace is None:
                    raise AttributeError(
                        "session_manager 缺少 conversation_store / db_path / workspace"
                    )
                db_path = workspace / "sessions.db"
            self._store = ConversationStore(db_path)
        self._binding_resolver = binding_resolver
        self._projector = ConversationStateProjector(self._store)

    def get_thread_by_session_key(self, session_key: str) -> ThreadRecord | None:
        return self._store.get_thread_by_legacy_session_key(session_key)

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        """Looks up a formal thread without exposing a legacy session key."""
        return self._store.get_thread(thread_id)

    def get_thread_for_runtime(
        self,
        runtime_key: str,
        *,
        thread_id: str = "",
    ) -> ThreadRecord | None:
        """Resolves a runtime adapter key to its formal thread identity."""
        clean_thread_id = str(thread_id or "").strip()
        if clean_thread_id:
            thread = self._store.get_thread(clean_thread_id)
            if thread is not None:
                return thread
        if str(runtime_key or "").startswith("thread:"):
            thread = self._store.get_thread(runtime_key)
            if thread is not None:
                return thread
        return self._store.get_thread_by_legacy_session_key(runtime_key)

    def ensure_desktop_thread(self, role_id: str) -> ThreadRecord:
        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id 不能为空")
        session_key = self._session_manager.role_session_key(clean_role_id)
        return self.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=session_key,
                role_id=clean_role_id,
                channel="desktop",
                chat_id="self",
            )
        )

    def ensure_thread_for_session(
        self,
        descriptor: LegacySessionDescriptor,
    ) -> ThreadRecord:
        existing = self._store.get_thread_by_legacy_session_key(descriptor.session_key)
        if existing is not None:
            return existing

        clean_session_key = str(descriptor.session_key or "").strip()
        if not clean_session_key:
            raise ValueError("session_key 不能为空")

        clean_role_id = str(descriptor.role_id or "").strip()
        clean_channel = str(descriptor.channel or "").strip()
        clean_chat_id = str(descriptor.chat_id or "").strip()

        if clean_session_key.startswith("role:") or clean_channel == "desktop":
            resolved_role_id = clean_role_id or clean_session_key.removeprefix("role:").strip()
            return self._build_desktop_thread(
                resolved_role_id,
                session_key=clean_session_key,
                created_at=descriptor.created_at,
                updated_at=descriptor.updated_at,
            )

        if clean_channel and clean_chat_id:
            resolved_role_id = clean_role_id or self._resolve_role_id(
                clean_channel,
                clean_chat_id,
                dict(descriptor.metadata or {}),
            )
            if resolved_role_id:
                return self._build_network_thread(
                    resolved_role_id,
                    channel=clean_channel,
                    chat_id=clean_chat_id,
                    session_key=clean_session_key,
                    created_at=descriptor.created_at,
                    updated_at=descriptor.updated_at,
                )

        return self._build_unresolved_thread(
            session_key=clean_session_key,
            channel=clean_channel or "unknown",
            external_id=clean_chat_id or clean_session_key,
            created_at=descriptor.created_at,
            updated_at=descriptor.updated_at,
        )

    def sync_session_messages_to_thread(
        self,
        session_key: str,
        *,
        role_id: str = "",
        channel: str = "",
        chat_id: str = "",
        created_at: str = "",
        updated_at: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ThreadRecord:
        thread = self.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=session_key,
                role_id=role_id,
                channel=channel,
                chat_id=chat_id,
                created_at=created_at,
                updated_at=updated_at,
                metadata=metadata,
            )
        )
        self._store.assign_legacy_messages_to_thread(session_key, thread.id)
        self._projector.project_thread(thread)
        return thread

    def has_external_message(self, thread_id: str, external_message_id: str) -> bool:
        """Checks inbound channel idempotency against archived thread messages."""
        return self._store.has_external_message(thread_id, external_message_id)

    @staticmethod
    def serialize_thread(thread: ThreadRecord) -> dict[str, Any]:
        return {
            "id": thread.id,
            "role_id": thread.role_id,
            "contact_id": thread.contact_id,
            "channel": thread.channel,
            "kind": thread.thread_kind,
            "external_thread_id": thread.external_thread_id,
            "legacy_session_key": thread.legacy_session_key,
            "archived": thread.archived,
            "metadata": dict(thread.metadata),
            "created_at": thread.created_at,
            "updated_at": thread.updated_at,
        }

    def _resolve_role_id(
        self,
        channel: str,
        chat_id: str,
        metadata: dict[str, Any],
    ) -> str:
        if self._binding_resolver is not None:
            try:
                resolved = str(self._binding_resolver(channel, chat_id) or "").strip()
            except KeyError:
                resolved = ""
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
    ) -> ThreadRecord:
        if not role_id:
            raise ValueError("desktop thread 需要 role_id")
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
    ) -> ThreadRecord:
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
    ) -> ThreadRecord:
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
