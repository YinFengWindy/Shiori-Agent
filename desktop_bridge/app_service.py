from __future__ import annotations

from typing import Any

from conversation.service import ConversationService
from core.roles import RoleAggregateService, RoleRelationshipRuntimeService
from session.manager import Session, SessionManager


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
    ) -> Session:
        session_key = self.normalize_desktop_session_key(chat_id)
        role_id = self.role_id_from_desktop_session_key(session_key)
        session = self.session_manager.get_or_create(session_key)
        normalized_message = str(message or "")
        normalized_media = [item for item in (media or []) if str(item).strip()]
        if self._is_existing_desktop_push(
            session,
            message=normalized_message,
            media=normalized_media,
        ):
            return session
        original_length = len(session.messages)
        original_updated_at = session.updated_at
        session.add_message(
            "assistant",
            normalized_message,
            media=normalized_media or None,
            proactive=True,
            tools_used=["message_push"],
        )
        try:
            await self.session_manager.save_async(session)
        except Exception:
            del session.messages[original_length:]
            session.updated_at = original_updated_at
            raise
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
    ) -> Session:
        original_length = len(session.messages)
        original_updated_at = session.updated_at
        session.add_message(
            "user",
            content,
            media=media or None,
            metadata=self.build_desktop_user_message_metadata(metadata),
        )
        try:
            await self.session_manager.append_messages(session, session.messages[-1:])
        except Exception:
            del session.messages[original_length:]
            session.updated_at = original_updated_at
            raise
        self.sync_desktop_session_thread(session, role_id=role_id)
        return await self._apply_post_persist_runtime_effects(
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

    def build_desktop_user_message_metadata(
        self,
        metadata: dict[str, object] | None,
    ) -> dict[str, object]:
        next_metadata = dict(metadata or {})
        next_metadata.pop("persisted_user_content", None)
        next_metadata.setdefault("source", "desktop")
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
        thread = self.conversation_service.sync_session_messages_to_thread(
            session.key,
            role_id=role_id,
            channel="desktop",
            chat_id="self",
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            metadata=dict(session.metadata),
        )
        session.metadata.setdefault("thread_id", thread.id)
        for message in session.messages:
            if not str(message.get("thread_id") or "").strip():
                message["thread_id"] = thread.id

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
    def _is_existing_desktop_push(
        session: Session,
        *,
        message: str,
        media: list[str],
    ) -> bool:
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
