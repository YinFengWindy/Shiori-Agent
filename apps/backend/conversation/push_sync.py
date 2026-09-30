from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

from bus.event_bus import EventBus
from bus.events_lifecycle import (
    ExternalImagePushed,
    ExternalTextPushed,
    ProactiveMessageCommitted,
)
from conversation.service import ConversationService, LegacySessionDescriptor
from session.manager import Session, SessionManager
from session.manager.models import build_session_message


class LiveTurnPushes(Protocol):
    """The pushes a live turn holds until it commits (the agent's turn push drafts)."""

    def append(
        self,
        message: dict[str, Any],
        *,
        owner: object,
        if_abandoned: Callable[[], Awaitable[None]] | None = None,
    ) -> None: ...


class ExternalPushSyncService:
    """Records pushes delivered through external channels in the role's session.

    The role owns the chat it pushed to, so a push is stored in the role's
    session (``role_session_key(role_id)``, whatever session the sender ran
    in) under the network thread of that chat, and announced with
    ``ProactiveMessageCommitted``. A push a live turn owns is committed with
    that turn instead: ``live_turn_pushes(session_key)`` finds it.
    """

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        event_bus: EventBus,
        live_turn_pushes: Callable[[str], LiveTurnPushes | None],
        conversation_service: ConversationService | None = None,
    ) -> None:
        self._sessions = session_manager
        self._event_bus = event_bus
        self._live_turn_pushes = live_turn_pushes
        self._conversations = conversation_service or ConversationService(
            session_manager
        )
        event_bus.on(ExternalImagePushed, self.handle_image_pushed)
        event_bus.on(ExternalTextPushed, self.handle_text_pushed)

    async def handle_image_pushed(
        self,
        event: ExternalImagePushed,
    ) -> ExternalImagePushed:
        """Records a delivered image once, with its turn or at once.

        Same rule as a text: a push made during a live turn becomes one of
        that turn's drafts (still recorded if the turn fails); an image pushed
        from a turn no live turn owns (e.g. a background task's report) is
        stored at once.
        """

        if event.already_persisted:
            self._validate_existing_message(event)
            return event
        media = [event.image]
        drafts = (
            self._live_turn_pushes(event.session_key) if event.attach_to_turn else None
        )
        if drafts is not None:
            drafts.append(
                self._push_message(event, content="", media=media),
                owner=self,
                if_abandoned=lambda: self._persist_push(event, content="", media=media),
            )
            return event
        await self._persist_push(event, content="", media=media)
        return event

    async def handle_text_pushed(self, event: ExternalTextPushed) -> ExternalTextPushed:
        """Records a delivered text once, with its turn or at once.

        A push made during a live turn becomes one of that turn's drafts,
        committed with its messages (and still recorded if the turn fails). A
        host-owned send, or a turn push no live turn owns (e.g. a background
        task's report), is stored at once. A delivery whose ``delivery_key``
        the role session already holds is not stored again.
        """
        drafts = self._live_turn_pushes(event.session_key) if event.in_turn else None
        if drafts is not None:
            drafts.append(
                self._push_message(event, content=event.text, media=_text_media(event)),
                owner=self,
                if_abandoned=lambda: self._persist_text(event),
            )
            return event
        await self._persist_text(event)
        return event

    async def _persist_text(self, event: ExternalTextPushed) -> None:
        session = self._sessions.get_or_create(self._role_session_key(event))
        if event.delivery_key and any(
            (message.get("metadata") or {}).get("delivery_key") == event.delivery_key
            for message in session.messages
        ):
            # A retried delivery: the first send is already recorded.
            return
        await self._persist_push(event, content=event.text, media=_text_media(event))

    def _role_session_key(self, event: ExternalImagePushed | ExternalTextPushed) -> str:
        """The role's session, which records every push of the role."""
        return self._sessions.role_session_key(event.role_id)

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
        metadata: dict[str, Any] = {
            **self._build_source_metadata(event, thread_id=thread.id)
        }
        tool = "message_push"
        if isinstance(event, ExternalTextPushed):
            tool = event.tool
            metadata.update(source=tool, sender_id=tool, **event.message_metadata)
            if event.delivery_key:
                metadata["delivery_key"] = event.delivery_key
            if event.external_message_id:
                metadata["external_message_id"] = event.external_message_id
        return build_session_message(
            "assistant",
            content,
            media=media,
            proactive=True,
            tools_used=[tool],
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
        session_key = self._role_session_key(event)
        session = self._sessions.get_or_create(session_key)
        session.add_message(**self._push_message(event, content=content, media=media))
        pushed = session.messages[-1]
        await self._sessions.append_messages(session, [pushed])
        await self._event_bus.fanout(
            ProactiveMessageCommitted(
                session_key=session_key,
                channel=event.channel,
                role_id=event.role_id,
                thread_id=str(pushed["thread_id"]),
                message_id=str(pushed["id"]),
            )
        )

    def _validate_existing_message(self, event: ExternalImagePushed) -> None:
        session = self._sessions.get_or_create(self._role_session_key(event))
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

    def _build_source_metadata(
        self,
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
            "session_key_override": self._role_session_key(event),
        }


def _text_media(event: ExternalTextPushed) -> list[str] | None:
    """The images sent in the same message as a pushed text, if any."""
    return list(event.media) or None
