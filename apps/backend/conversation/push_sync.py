from __future__ import annotations

from typing import Any, cast

from agent.lifecycle.types import AfterReasoningCtx
from bus.event_bus import EventBus
from bus.events_lifecycle import (
    ExternalImagePushed,
    ExternalTextPushed,
    ProactiveMessageCommitted,
)
from agent.turns.desktop_pushes import current_desktop_pushes
from conversation.service import ConversationService, LegacySessionDescriptor
from session.manager import Session, SessionManager
from session.manager.models import build_session_message


class ExternalPushSyncService:
    """Persists externally pushed images, and host-owned pushed texts, into the role session.

    Each is stored in the role's session under the network thread of the chat
    it went to, then announced with ``ProactiveMessageCommitted``.
    """

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        event_bus: EventBus,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self._sessions = session_manager
        self._event_bus = event_bus
        self._conversations = conversation_service or ConversationService(
            session_manager
        )
        self._pending_turn_images: dict[str, list[str]] = {}
        event_bus.on(ExternalImagePushed, self.handle_image_pushed)
        event_bus.on(ExternalTextPushed, self.handle_text_pushed)
        event_bus.on(AfterReasoningCtx, self.attach_turn_images)

    async def handle_image_pushed(
        self,
        event: ExternalImagePushed,
    ) -> ExternalImagePushed:
        """Queues turn-owned images or persists background deliveries immediately."""

        self._validate_role_session(event)
        if event.already_persisted:
            self._validate_existing_message(event)
            return event
        if event.attach_to_turn:
            pending = self._pending_turn_images.setdefault(event.session_key, [])
            if event.image not in pending:
                pending.append(event.image)
            return event

        await self._persist_push(event, content="", media=[event.image])
        return event

    async def handle_text_pushed(self, event: ExternalTextPushed) -> ExternalTextPushed:
        """Records a delivered text once, with its turn or at once.

        A push made during a turn becomes one of that turn's drafts, committed
        with its messages. A host-owned send, or a turn push no live turn owns
        (e.g. a background task's report), is stored at once. Either way a
        delivery already recorded (same platform message ID in the turn, same
        ``delivery_key`` in the session) is not stored again.
        """
        self._validate_role_session(event)
        drafts = current_desktop_pushes(event.session_key) if event.in_turn else None
        if drafts is not None:
            if not (
                event.external_message_id
                and _holds_delivery(
                    drafts.messages, "external_message_id", event.external_message_id
                )
            ):
                drafts.append(self._push_message(event, content=event.text), owner=self)
            return event
        session = self._sessions.get_or_create(event.session_key)
        if event.delivery_key and _holds_delivery(
            session.messages, "delivery_key", event.delivery_key
        ):
            # A retried delivery: the first send is already recorded.
            return event
        await self._persist_push(event, content=event.text, media=None)
        return event

    def _push_message(
        self,
        event: ExternalImagePushed | ExternalTextPushed,
        *,
        content: str,
        media: list[str] | None = None,
    ) -> dict[str, Any]:
        """A delivered push as a role message under the target chat's thread."""
        thread = self._conversations.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"{event.channel}:{event.chat_id}",
                role_id=event.role_id,
                channel=event.channel,
                chat_id=event.chat_id,
            )
        )
        metadata: dict[str, str] = self._build_source_metadata(
            event, thread_id=thread.id
        )
        if isinstance(event, ExternalTextPushed):
            if event.delivery_key:
                metadata["delivery_key"] = event.delivery_key
            if event.external_message_id:
                metadata["external_message_id"] = event.external_message_id
        return build_session_message(
            "assistant",
            content,
            media=media,
            proactive=True,
            tools_used=["message_push"],
            thread_id=thread.id,
            sender_role="assistant",
            metadata=metadata,
        )

    async def _persist_push(
        self,
        event: ExternalImagePushed | ExternalTextPushed,
        *,
        content: str,
        media: list[str] | None,
    ) -> None:
        """Appends one delivered push to the role session under the chat's thread."""
        session = self._sessions.get_or_create(event.session_key)
        session.add_message(**self._push_message(event, content=content, media=media))
        pushed = session.messages[-1]
        await self._sessions.append_messages(session, [pushed])
        await self._event_bus.fanout(
            ProactiveMessageCommitted(
                session_key=event.session_key,
                channel=event.channel,
                role_id=event.role_id,
                thread_id=str(pushed["thread_id"]),
                message_id=str(pushed["id"]),
            )
        )

    def attach_turn_images(self, ctx: AfterReasoningCtx) -> AfterReasoningCtx:
        """Attaches already-delivered images to persistence without resending them."""

        pending = self._pending_turn_images.pop(ctx.session_key, [])
        for image in pending:
            if image not in ctx.persisted_media:
                ctx.persisted_media.append(image)
        return ctx

    def _validate_role_session(
        self, event: ExternalImagePushed | ExternalTextPushed
    ) -> None:
        expected = self._sessions.role_session_key(event.role_id)
        if event.session_key != expected:
            raise ValueError(
                f"外部推送的 session 不属于角色 {event.role_id}: {event.session_key}"
            )

    def _validate_existing_message(self, event: ExternalImagePushed) -> None:
        session = self._sessions.get_or_create(event.session_key)
        if self._last_message_contains(session, event):
            return
        raise RuntimeError("外部图片已发送，但预写入的共享会话消息不存在")

    @staticmethod
    def _last_message_contains(session: Session, event: ExternalImagePushed) -> bool:
        if not session.messages:
            return False
        message = session.messages[-1]
        metadata = message.get("metadata")
        source = cast(dict[str, Any], metadata) if isinstance(metadata, dict) else {}
        same_transport = (
            str(source.get("transport_channel") or "") == event.channel
            and str(source.get("transport_chat_id") or "") == event.chat_id
        )
        multi_transport_proactive = (
            message.get("proactive") is True
            and str(source.get("source") or "") == "proactive"
        )
        return (
            message.get("role") == "assistant"
            and event.image in list(message.get("media") or [])
            and (same_transport or multi_transport_proactive)
        )

    @staticmethod
    def _build_source_metadata(
        event: ExternalImagePushed | ExternalTextPushed,
        *,
        thread_id: str,
    ) -> dict[str, str]:
        return {
            "source": "message_push",
            "sender_id": "message_push",
            "chat_type": "unknown",
            "context_channel": event.channel,
            "context_chat_id": event.chat_id,
            "transport_channel": event.channel,
            "transport_chat_id": event.chat_id,
            "role_id": event.role_id,
            "thread_id": thread_id,
            "session_key_override": event.session_key,
        }


def _holds_delivery(messages: list[dict[str, Any]], key: str, value: str) -> bool:
    """Whether one of ``messages`` records the delivery whose metadata ``key`` is ``value``."""
    return any(
        (message.get("metadata") or {}).get(key) == value for message in messages
    )
