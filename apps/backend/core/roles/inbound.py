from __future__ import annotations

from pathlib import Path

from bus.events import InboundMessage
from core.channels.hub import ChannelHub

from .services import RoleAggregateService
from .store import RoleStore


class InboundRoleRouter:
    """将 legacy channel 入站解析为 role-first 业务消息。"""

    def __init__(self, service: RoleAggregateService) -> None:
        self._hub = ChannelHub(service)

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
        return self._hub.route_inbound(message)


def route_inbound_by_role(
    service: RoleAggregateService,
    message: InboundMessage,
) -> InboundMessage:
    """函数式入口，便于在 channel 测试中直接调用。"""

    return InboundRoleRouter(service).route(message)
