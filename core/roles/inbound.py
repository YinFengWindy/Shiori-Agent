from __future__ import annotations

from pathlib import Path
from typing import Any

from bus.events import InboundMessage

from .services import RoleAggregateService
from .store import RoleStore


def _is_group_chat(metadata: dict[str, Any]) -> bool:
    return str(metadata.get("chat_type") or "").strip() == "group" or bool(
        metadata.get("is_group_chat")
    )


def _group_id(metadata: dict[str, Any], message: InboundMessage) -> str:
    value = str(metadata.get("group_id") or "").strip()
    if value:
        return value
    chat_id = str(message.chat_id or "").strip()
    if chat_id.startswith("gqq:"):
        return chat_id[len("gqq:") :].strip()
    return ""


def _member_id(metadata: dict[str, Any], message: InboundMessage) -> str:
    for key in ("group_member_id", "member_id", "sender_id"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return str(message.sender or "").strip()


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

        try:
            role_id = self._service.bindings.resolve_role_id(message.channel, message.chat_id)
        except KeyError:
            return message
        if _is_group_chat(metadata):
            group_id = _group_id(metadata, message)
            member_id = _member_id(metadata, message)
            if group_id and member_id:
                session_key = self._service.sessions.derive_group_member_session_key(
                    role_id,
                    group_id=group_id,
                    member_id=member_id,
                )
                metadata["is_group_chat"] = True
                metadata["group_id"] = group_id
                metadata["group_member_id"] = member_id
                metadata.setdefault("member_id", member_id)
                metadata["group_context_key"] = self._service.sessions.derive_group_context_key(
                    channel=message.channel,
                    group_id=group_id,
                )
            else:
                session_key = self._service.sessions.derive_session_key(role_id)
        else:
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
