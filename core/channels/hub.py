from __future__ import annotations

from pathlib import Path
from typing import Any

from bus.events import InboundMessage, OutboundMessage
from conversation.service import ConversationService, LegacySessionDescriptor
from core.roles.services import RoleAggregateService
from core.roles.store import RoleStore
from core.roles.world import RoleExecutionContext


class ChannelHub:
    """Coordinates role-bound channel routing and delivery bookkeeping."""

    def __init__(self, service: RoleAggregateService) -> None:
        self._service = service
        self._conversation = ConversationService(
            service.sessions._session_manager,
            binding_resolver=service.bindings.resolve_role_id,
        )

    @classmethod
    def from_workspace(cls, workspace: Path, *, session_manager) -> "ChannelHub":
        """Builds a hub from the current workspace and shared session manager."""
        return cls(
            RoleAggregateService.from_runtime(
                workspace=workspace,
                role_store=RoleStore(workspace),
                session_manager=session_manager,
            )
        )

    def route_inbound(self, message: InboundMessage) -> InboundMessage:
        """Maps a bound channel message onto its formal network thread session."""
        metadata = dict(message.metadata or {})
        if message.channel == "desktop":
            return message

        role_id = str(metadata.get("role_id") or "").strip()
        if not role_id:
            try:
                role_id = self._service.bindings.resolve_role_id(
                    message.channel,
                    message.chat_id,
                )
            except KeyError:
                return message
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
        external_message_id = str(
            metadata.get("external_message_id") or metadata.get("message_id") or ""
        ).strip()
        if external_message_id:
            metadata["external_message_id"] = external_message_id
            if self._conversation.has_external_message(thread.id, external_message_id):
                metadata["conversation_duplicate"] = True
        session = self._service.sessions._session_manager.sync_thread_session_metadata(
            thread.id,
            role_id=role.id,
            role_name=role.name,
            role_prompt=role.system_prompt,
            thread_id=thread.id,
            role_runtime_config=role.runtime_config,
            context_channel=message.channel,
            context_chat_id=message.chat_id,
            transport_channel=message.channel,
            transport_chat_id=message.chat_id,
        )
        metadata["role_id"] = role_id
        metadata["thread_id"] = thread.id
        metadata["session_key_override"] = session.key
        metadata.setdefault("context_channel", message.channel)
        metadata.setdefault("context_chat_id", message.chat_id)
        metadata.setdefault("transport_channel", message.channel)
        metadata.setdefault("transport_chat_id", message.chat_id)
        metadata.setdefault("source", "role_channel_binding")
        context = RoleExecutionContext.create(
            role=role,
            thread_id=thread.id,
            transport_channel=message.channel,
            transport_chat_id=message.chat_id,
            source=str(metadata["source"]),
            work_kind="passive_turn",
            request_id=external_message_id,
        )
        metadata.update(context.to_metadata())
        return InboundMessage(
            channel=message.channel,
            sender=message.sender,
            chat_id=message.chat_id,
            content=message.content,
            timestamp=message.timestamp,
            media=list(message.media),
            metadata=metadata,
        )

    def is_sender_allowed(
        self,
        *,
        channel: str,
        chat_id: str,
        sender_id: str,
        sender_alias: str = "",
    ) -> bool:
        """Checks the owning role binding's allow-list before inbound handling."""
        binding = self._service.bindings.get_binding(channel, chat_id)
        if binding is None:
            return False
        role = self._service.repository.get_required(binding.role_id)
        config = next(
            item for item in role.channel_bindings
            if item.channel == channel and item.chat_id == chat_id
        )
        if not config.allow_from:
            return True
        allowed = set(config.allow_from)
        return sender_id in allowed or (sender_alias and sender_alias.lower() in {item.lower() for item in allowed})

    def has_binding(self, channel: str, chat_id: str) -> bool:
        """Returns whether a channel session belongs to any role."""
        return self._service.bindings.get_binding(channel, chat_id) is not None

    def resolve_runtime_session_key(self, channel: str, chat_id: str) -> str:
        """Resolves a channel control action to the thread currently owning it."""
        legacy_session_key = f"{channel}:{chat_id}"
        thread = self._conversation.get_thread_by_session_key(legacy_session_key)
        return thread.id if thread is not None else legacy_session_key

    def mark_delivery(
        self,
        message: OutboundMessage,
        *,
        default_channel: str,
        delivery_status: str,
        external_message_id: str = "",
    ) -> dict[str, Any] | None:
        """Writes the latest assistant delivery state back to the owning session."""
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        session_key = str(
            metadata.get("session_key_override")
            or metadata.get("session_key")
            or f"{default_channel}:{message.chat_id}"
        ).strip()
        thread_id = str(metadata.get("thread_id") or "").strip()
        marker = getattr(
            self._service.sessions._session_manager,
            "mark_latest_assistant_delivery",
            None,
        )
        if not callable(marker):
            return None
        return marker(
            session_key,
            thread_id=thread_id,
            delivery_status=delivery_status,
            external_message_id=external_message_id,
        )
