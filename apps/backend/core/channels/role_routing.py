"""Turns admitted external input into a role turn through its source thread.

Channel account intake (``ChannelHub``) and plugin-submitted external turns
(``agent.plugin_host.external_turns``) share this one implementation: the
source thread, the projection onto the role's session and the role execution
context are built the same way, so both are judged and stored identically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from conversation.models import ThreadRecord
from conversation.service import ConversationService, LegacySessionDescriptor
from core.common.channel_directory import ChannelDirectory
from core.roles.role_runtime import RoleExecutionContext
from core.roles.services import RoleAggregateService
from core.roles.store import RoleStore
from session.manager import SessionManager
from shiori_sdk.channels.chat_types import is_group_chat_type
from shiori_sdk.channels.message_source import (
    GROUP_NAME_KEY,
    SENDER_NAME_KEY,
    display_name,
)
from shiori_sdk.channels.projection import project_inbound
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.messages import InboundMessage

# Turn metadata flag: the thread already holds this platform message ID.
CONVERSATION_DUPLICATE_KEY = "conversation_duplicate"


class RoleTurnRouter:
    """Projects admitted input onto a role's session through its source thread."""

    def __init__(
        self,
        service: RoleAggregateService,
        *,
        channel_directory: ChannelDirectory,
    ) -> None:
        self._service = service
        self._channel_directory = channel_directory
        self._conversation = ConversationService(service.sessions._session_manager)

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        *,
        session_manager: SessionManager,
        role_store: RoleStore,
        channel_directory: ChannelDirectory,
    ) -> "RoleTurnRouter":
        """Builds a router over the shared role store and session manager."""
        return cls(
            RoleAggregateService.from_runtime(
                workspace=workspace,
                role_store=role_store,
                session_manager=session_manager,
            ),
            channel_directory=channel_directory,
        )

    @property
    def conversation(self) -> ConversationService:
        """The conversation store the source threads live in."""
        return self._conversation

    def network_turn_context(
        self, message: InboundMessage, role_id: str, *, source: str
    ) -> RoleExecutionContext:
        """The context of a turn of ``role_id`` in the thread of ``message``'s chat.

        Built from the role's current configuration without touching any
        storage, so a caller can take the role's turn gate before routing
        (``route(..., context=)``). The thread is the chat's
        ``network_thread_id``; ``request_id`` is the platform message ID in
        ``external_message_id``. Raises ``RoleNotFoundError`` for an unknown
        role.
        """
        return RoleExecutionContext.create(
            role=self._service.repository.get_required(role_id),
            thread_id=network_thread_id(role_id, message.channel, message.chat_id),
            transport_channel=message.channel,
            transport_chat_id=message.chat_id,
            source=source,
            work_kind="passive_turn",
            request_id=str(message.metadata.get("external_message_id") or ""),
        )

    def route(
        self,
        message: InboundMessage,
        role_id: str,
        metadata: dict[str, Any],
        *,
        context: RoleExecutionContext | None = None,
    ) -> InboundMessage:
        """``message`` as a turn of ``role_id`` in the thread of its chat.

        ``metadata`` is the admitted metadata (host flags included) and must
        carry ``source``. The chat's thread is created when missing and the
        contact is renamed by the reported group or sender name. A platform
        message ID the thread already holds marks the turn
        ``CONVERSATION_DUPLICATE_KEY``; the caller decides whether to run it.
        The returned metadata carries the full ``RoleExecutionContext``: the
        given ``context`` (from ``network_turn_context``, which must name the
        routed thread), else a new one. Raises ``RoleNotFoundError`` for an
        unknown role.
        """
        role = self._service.repository.get_required(role_id)
        thread = self._conversation.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"{message.channel}:{message.chat_id}",
                role_id=role_id,
                channel=message.channel,
                chat_id=message.chat_id,
                metadata=metadata,
            )
        )
        if context is not None and (
            context.role_id != role_id or context.thread_id != thread.id
        ):
            raise ValueError("角色回合上下文与路由到的会话不一致")
        self._service.sessions.open_by_role(role)
        routed = self.project(message, role_id, thread, metadata)
        external_message_id = str(routed.metadata.get("external_message_id") or "")
        if external_message_id and self._conversation.has_external_message(
            thread.id, external_message_id
        ):
            routed.metadata[CONVERSATION_DUPLICATE_KEY] = True
        # A replayed duplicate carries no newer name than the original did.
        if not routed.metadata.get(CONVERSATION_DUPLICATE_KEY):
            self.remember_contact_name(thread, routed.metadata)
        if context is None:
            context = RoleExecutionContext.create(
                role=role,
                thread_id=thread.id,
                transport_channel=message.channel,
                transport_chat_id=message.chat_id,
                source=str(routed.metadata["source"]),
                work_kind="passive_turn",
                request_id=external_message_id,
            )
        routed.metadata.update(context.to_metadata())
        return routed

    def project(
        self,
        message: InboundMessage,
        role_id: str,
        thread: ThreadRecord,
        metadata: dict[str, Any],
    ) -> InboundMessage:
        """``message`` addressed to ``role_id``'s session through ``thread``."""
        return project_inbound(
            message,
            metadata,
            role_id=role_id,
            thread_id=thread.id,
            session_key=self._service.sessions.derive_session_key(role_id),
            default_chat_type=self._channel_directory.default_chat_type(
                message.channel
            ),
        )

    def remember_contact_name(
        self, thread: ThreadRecord, metadata: dict[str, Any]
    ) -> None:
        """Names the contact by the group's name, or a private chat's sender's.

        Whichever the plugin reported with this message; none keeps the name.
        """
        name_key = (
            GROUP_NAME_KEY
            if is_group_chat_type(metadata.get("chat_type"))
            else SENDER_NAME_KEY
        )
        name = display_name(metadata.get(name_key))
        if name is not None:
            self._conversation.remember_contact_name(thread, name)
