from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from bus.event_bus import EventBus
from bus.events_lifecycle import ExternalTextPushed, InitiatedMessageCommitted
from conversation.service import ConversationService, LegacySessionDescriptor
from session.manager import SessionManager
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
    ``InitiatedMessageCommitted`` (``source="push"``, the tool in
    ``tools_used``). A push a live turn owns is committed with
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
        event_bus.on(ExternalTextPushed, self.handle_text_pushed)

    async def handle_text_pushed(self, event: ExternalTextPushed) -> ExternalTextPushed:
        """Records a delivered text once, with its turn or at once.

        A push made during a live turn becomes one of that turn's drafts,
        committed with its messages; if the turn never commits, ``persist``
        records it then. A host-owned send, or a turn push no live turn owns
        (e.g. a background task's report), is stored at once.
        """
        message = self._push_message(event)

        async def persist():
            # The same draft retains its delivery time and host turn identity
            # when failure/cancellation records a push that was already sent.
            await self._persist_push(event, message)

        drafts = self._live_turn_pushes(event.session_key) if event.in_turn else None
        if drafts is None:
            await persist()
            return event
        drafts.append(
            message,
            owner=self,
            if_abandoned=persist,
        )
        return event

    def _role_session_key(self, event: ExternalTextPushed) -> str:
        """The role's session, which records every push of the role."""
        return self._sessions.role_session_key(event.role_id)

    def _push_message(self, event: ExternalTextPushed) -> dict[str, Any]:
        """A delivered push as a role message under the target chat's thread.

        The sending tool (``event.tool``) is the message's source, sender and
        only tool used; ``message_metadata`` is applied over those defaults
        and carries the chat type.
        """
        thread = self._conversations.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"{event.channel}:{event.chat_id}",
                role_id=event.role_id,
                channel=event.channel,
                chat_id=event.chat_id,
            )
        )
        metadata: dict[str, Any] = {
            **self._build_source_metadata(event, thread_id=thread.id),
            **event.message_metadata,
        }
        if event.external_message_id:
            metadata["external_message_id"] = event.external_message_id
        return build_session_message(
            "assistant",
            event.text,
            media=list(event.media) or None,
            # Model-requested sends are proactive; host media supplements retain
            # the reply's non-proactive classification.
            proactive=event.proactive,
            tools_used=[event.tool],
            thread_id=thread.id,
            sender_role="assistant",
            metadata=metadata,
        )

    async def _persist_push(
        self,
        event: ExternalTextPushed,
        message: dict[str, Any],
    ) -> None:
        """Appends one delivered push to the role session under the chat's thread."""
        session_key = self._role_session_key(event)
        session = self._sessions.get_or_create(session_key)
        # Without before_commit the append always commits.
        _ = await self._sessions.append_messages(
            session,
            [message],
            pending_messages=True,
        )
        await self._event_bus.fanout(
            InitiatedMessageCommitted(
                session_key=session_key,
                channel=event.channel,
                role_id=event.role_id,
                thread_id=str(message["thread_id"]),
                chat_id=event.chat_id,
                assistant_response=event.text,
                tools_used=tuple(message.get("tools_used") or ()),
                message_id=str(message["id"]),
                source="push",
            )
        )

    def _build_source_metadata(
        self,
        event: ExternalTextPushed,
        *,
        thread_id: str,
    ) -> dict[str, str]:
        return {
            "source": event.tool,
            "sender_id": event.tool,
            "context_channel": event.channel,
            "context_chat_id": event.chat_id,
            "transport_channel": event.channel,
            "transport_chat_id": event.chat_id,
            "role_id": event.role_id,
            "thread_id": thread_id,
            "session_key_override": self._role_session_key(event),
        }
