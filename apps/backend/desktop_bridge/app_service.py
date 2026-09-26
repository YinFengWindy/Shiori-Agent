from __future__ import annotations

from typing import Any

from conversation.service import ConversationService
from core.roles import RoleAggregateService, RoleRelationshipRuntimeService
from session.manager import Session, SessionManager
from session.manager.models import build_session_message


class DesktopAppService:
    """Owns desktop-facing application use cases behind the bridge RPC layer."""

    def __init__(
        self,
        *,
        role_service: RoleAggregateService,
        session_manager: SessionManager,
        conversation_service: ConversationService,
        relationship_runtime: RoleRelationshipRuntimeService | None = None,
        presence: Any | None = None,
    ) -> None:
        self.role_service = role_service
        self.session_manager = session_manager
        self.conversation_service = conversation_service
        self.relationship_runtime = relationship_runtime
        self.presence = presence

    async def open_role_session(self, role_id: str):
        aggregate = await self.role_service.open_role_async(role_id)
        self.sync_desktop_session_thread(aggregate.session, role_id=aggregate.role.id)
        return aggregate

    async def update_display_state(
        self,
        role_id: str,
        *,
        active_illustration: str | None,
    ) -> Session:
        aggregate = await self.role_service.open_role_async(role_id)
        session = self.role_service.sessions.update_display_state(
            aggregate.role,
            active_illustration=active_illustration,
        )
        self.sync_desktop_session_thread(session, role_id=aggregate.role.id)
        return session

    async def apply_desktop_push(
        self,
        chat_id: str,
        *,
        message: str = "",
        media: list[str] | None = None,
        delivery_key: str = "",
        already_persisted: bool = False,
    ) -> Session:
        """Validates pushes and persists only deliveries not owned by a turn commit."""
        normalized_message = str(message or "")
        normalized_media = [item for item in (media or []) if str(item).strip()]
        if not normalized_message.strip() and not normalized_media:
            raise ValueError("desktop push 必须包含非空文本或媒体")
        session_key = self.normalize_desktop_session_key(chat_id)
        role_id = self.role_id_from_desktop_session_key(session_key)
        session = self.session_manager.get_or_create(session_key)
        if already_persisted:
            # A turn commit owns this message. A missing commit is an error, not
            # permission for the transport to become a second persistence owner.
            if not delivery_key or not self._has_delivery(session, delivery_key):
                raise ValueError("Desktop push references an uncommitted delivery")
            return await self._finish_desktop_push(session, role_id=role_id)
        if self._is_existing_desktop_push(
            session,
            message=normalized_message,
            media=normalized_media,
            delivery_key=delivery_key,
        ):
            return session
        original_length = len(session.messages)
        original_updated_at = session.updated_at
        draft = self.build_desktop_push_message(
            session.key,
            message=normalized_message,
            media=normalized_media,
            delivery_key=delivery_key,
        )
        session.add_message(**draft)
        try:
            await self.session_manager.save_async(session)
        except Exception:
            del session.messages[original_length:]
            session.updated_at = original_updated_at
            raise
        return await self._finish_desktop_push(session, role_id=role_id)

    def validate_desktop_push_target(self, chat_id: str) -> None:
        """Accept a turn-owned desktop delivery without exposing pending messages."""
        session_key = self.normalize_desktop_session_key(chat_id)
        self.role_id_from_desktop_session_key(session_key)

    def build_desktop_push_message(
        self,
        session_key: str,
        *,
        message: str = "",
        media: list[str] | None = None,
        delivery_key: str = "",
    ) -> dict[str, Any]:
        """Builds the same private desktop message for immediate and turn commits."""
        return build_session_message(
            "assistant",
            message,
            media=media,
            proactive=True,
            tools_used=["message_push"],
            metadata=self.build_desktop_user_message_metadata(
                {"delivery_key": delivery_key} if delivery_key else None,
                role_id=self.role_id_from_desktop_session_key(session_key),
                chat_id=session_key,
            ),
        )

    async def finish_queued_desktop_push(self, session_key: str) -> None:
        """Runs desktop presence/projection effects after a passive turn commit."""
        await self._finish_desktop_push(
            self.session_manager.get_or_create(session_key),
            role_id=self.role_id_from_desktop_session_key(session_key),
        )

    async def _finish_desktop_push(self, session: Session, *, role_id: str) -> Session:
        self.sync_desktop_session_thread(session, role_id=role_id)
        return await self._apply_post_persist_runtime_effects(
            session,
            record_presence=(
                self.presence.record_proactive_sent
                if self.presence is not None
                else None
            ),
            handle_relationship=(
                self.relationship_runtime.handle_proactive_sent
                if self.relationship_runtime is not None
                else None
            ),
        )

    async def persist_desktop_user_message(
        self,
        *,
        session: Session,
        role_id: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
    ) -> dict[str, Any]:
        """Persists a user message and returns it after all runtime effects finish."""
        original_length = len(session.messages)
        original_updated_at = session.updated_at
        session.add_message(
            "user",
            content,
            media=media or None,
            metadata=self.build_desktop_user_message_metadata(
                metadata,
                role_id=role_id,
                chat_id=session.key,
            ),
        )
        # Other writers can append while persistence or runtime effects await.
        persisted_message = session.messages[original_length]
        try:
            await self.session_manager.append_messages(session, [persisted_message])
        except Exception:
            del session.messages[original_length:]
            session.updated_at = original_updated_at
            raise
        self.sync_desktop_session_thread(session, role_id=role_id)
        _ = await self._apply_post_persist_runtime_effects(
            session,
            record_presence=(
                self.presence.record_user_message if self.presence is not None else None
            ),
            handle_relationship=(
                self.relationship_runtime.handle_user_message
                if self.relationship_runtime is not None
                else None
            ),
        )
        return persisted_message

    def build_desktop_user_message_metadata(
        self,
        metadata: dict[str, object] | None,
        *,
        role_id: str = "",
        chat_id: str = "",
    ) -> dict[str, object]:
        next_metadata = dict(metadata or {})
        next_metadata.pop("persisted_user_content", None)
        next_metadata.setdefault("source", "desktop")
        next_metadata.setdefault("sender_id", "desktop")
        next_metadata.setdefault("chat_type", "desktop")
        if role_id:
            thread = self.conversation_service.ensure_desktop_thread(role_id)
            next_metadata["role_id"] = role_id
            next_metadata["thread_id"] = thread.id
            next_metadata.setdefault("context_channel", "desktop")
            next_metadata.setdefault("context_chat_id", chat_id or f"role:{role_id}")
            next_metadata.setdefault("transport_channel", "desktop")
            next_metadata.setdefault("transport_chat_id", chat_id or f"role:{role_id}")
        return next_metadata

    def normalize_desktop_session_key(self, chat_id: str) -> str:
        normalized = str(chat_id or "").strip()
        if normalized.startswith("role:"):
            return normalized
        if normalized:
            return self.role_service.sessions.derive_session_key(normalized)
        raise ValueError("desktop proactive chat_id 不能为空")

    def role_id_from_desktop_session_key(self, session_key: str) -> str:
        clean_key = str(session_key or "").strip()
        if not clean_key.startswith("role:"):
            return ""
        return clean_key.removeprefix("role:").strip()

    def sync_desktop_session_thread(self, session: Session, *, role_id: str) -> None:
        thread = self.conversation_service.ensure_desktop_thread(role_id)
        self.conversation_service.project_thread(thread)

    async def _apply_post_persist_runtime_effects(
        self,
        session: Session,
        *,
        record_presence,
        handle_relationship,
    ) -> Session:
        if record_presence is not None:
            record_presence(session.key)
        metadata_changed = False
        if handle_relationship is not None and self.relationship_runtime is not None:
            handle_relationship(session.key)
            enriched_metadata = self.relationship_runtime.enrich_session_metadata(
                dict(session.metadata),
            )
            if enriched_metadata != session.metadata:
                session.metadata = enriched_metadata
                metadata_changed = True
        if metadata_changed:
            await self.session_manager.save_async(session)
        return session

    @staticmethod
    def _has_delivery(session: Session, delivery_key: str) -> bool:
        return any(
            item.get("role") == "assistant"
            and (item.get("metadata") or {}).get("delivery_key") == delivery_key
            for item in session.messages
        )

    @staticmethod
    def _is_existing_desktop_push(
        session: Session,
        *,
        message: str,
        media: list[str],
        delivery_key: str = "",
    ) -> bool:
        if delivery_key:
            return DesktopAppService._has_delivery(session, delivery_key)
        if not session.messages:
            return False
        last_message = session.messages[-1]
        if last_message.get("role") != "assistant" or not last_message.get("proactive"):
            return False
        if str(last_message.get("content") or "") != message:
            return False
        last_media = [
            str(item).strip()
            for item in list(last_message.get("media") or [])
            if str(item).strip()
        ]
        return last_media == media
