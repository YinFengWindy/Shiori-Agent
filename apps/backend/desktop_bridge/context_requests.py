"""Desktop context control never persists or submits the composer's draft."""

from agent.looping.core import AgentLoop
from agent.looping.core.context_window import context_unavailable
from bus.events import InboundMessage
from core.roles import RoleAggregateService
from .app_service import DesktopAppService
from .chat_service import DesktopChatService


class DesktopContextRequests:
    """Resolve desktop ownership once for both the ring and /compact."""

    def __init__(
        self,
        roles: RoleAggregateService,
        app: DesktopAppService,
        chat: DesktopChatService,
        loop: AgentLoop,
    ) -> None:
        self.roles, self.app, self.chat, self.loop = roles, app, chat, loop

    async def invoke(self, role_id: str, *, compact: bool = False) -> dict:
        """Use the role's user context and actual model without creating a turn."""
        aggregate = await self.roles.open_role_async(role_id)
        key = aggregate.session.key
        if self.chat.is_busy(key):
            return context_unavailable(key, "正在回复，请稍后重试", busy=True)
        metadata = self.app.build_desktop_user_message_metadata(
            {}, role_id=role_id, chat_id=key
        )
        return await self.loop.inspect_context_window(
            InboundMessage(
                channel="desktop",
                sender="user",
                chat_id=key,
                content="",
                metadata=metadata,
            ),
            key,
            compact=compact,
        )
