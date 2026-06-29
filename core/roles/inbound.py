from __future__ import annotations

from pathlib import Path
from typing import Any

from bus.events import InboundMessage

from .services import RoleAggregateService
from .store import RoleStore


class InboundRoleRouter:
    """将 legacy channel 入站解析为 role-first 业务消息。"""

    def __init__(self, service: RoleAggregateService) -> None:
        self._service = service

    @classmethod
    def from_workspace(cls, workspace: Path, *, session_manager) -> "InboundRoleRouter":
        return cls(
            RoleAggregateService.from_runtime(
                workspace=workspace,
                role_store=RoleStore(workspace),
                session_manager=session_manager,
            )
        )

    def route(self, message: InboundMessage) -> InboundMessage:
        metadata = dict(message.metadata or {})
        if str(metadata.get("role_id") or "").strip():
            return message
        if message.channel == "desktop":
            return message

        role_id = self._service.bindings.resolve_role_id(message.channel, message.chat_id)
        session_key = self._service.sessions.derive_session_key(role_id)
        metadata["role_id"] = role_id
        metadata["session_key_override"] = session_key
        metadata.setdefault("context_channel", message.channel)
        metadata.setdefault("context_chat_id", message.chat_id)
        metadata.setdefault("transport_channel", message.channel)
        metadata.setdefault("transport_chat_id", message.chat_id)
        metadata.setdefault("source", "legacy_channel_binding")
        return InboundMessage(
            channel=message.channel,
            sender=message.sender,
            chat_id=message.chat_id,
            content=message.content,
            timestamp=message.timestamp,
            media=list(message.media),
            metadata=metadata,
        )


def route_inbound_by_role(
    service: RoleAggregateService,
    message: InboundMessage,
) -> InboundMessage:
    """函数式入口，便于在 channel 测试中直接调用。"""

    return InboundRoleRouter(service).route(message)
