"""``CONVERSATION`` for one runtime generation.

The orchestrator is built when a reply is delivered, not when the generation
is assembled: account sending is registered after the plugin kernel is given
this object.
"""

from __future__ import annotations

from collections.abc import Callable

from agent.looping.ports import SessionServices
from agent.tools.account_delivery import shared_account_delivery
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import PushToolOutboundPort
from bus.event_bus import EventBus
from conversation.initiated import bound_turn_getters, commit_initiated_reply
from conversation.service import ConversationService
from core.desktop_presence import DesktopPresence
from core.roles.affection_access import AffectionGetter
from core.roles.reply_policy import ReplyPolicyGetter
from core.roles.store import RoleStore
from proactive_v2.target_selection import ProactiveTargetResolver
from session.manager import SessionManager
from shiori_sdk.core.conversation import InitiatedReply
from shiori_sdk.core.sessions import Presence


def orchestrator_for(
    *,
    session_manager: SessionManager,
    presence: Presence | None,
    push_tool: MessagePushTool,
    event_bus: EventBus | None,
    tools: ToolRegistry,
    role_store: RoleStore,
    desktop_presence: DesktopPresence,
) -> TurnOrchestrator:
    """The same delivery wiring a proactive loop uses for one initiated reply."""
    return TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=session_manager,
                presence=presence,
                conversation_service=ConversationService(session_manager),
            ),
            outbound=PushToolOutboundPort(push_tool),
            event_bus=event_bus,
            account_delivery=shared_account_delivery(tools),
            bound_chat_target=ProactiveTargetResolver(
                roles=role_store,
                conversations=session_manager.conversation_store,
                desktop_presence=desktop_presence,
            ).bound_chat_target,
            role_lookup=role_store.get_role,
        )
    )


class HostConversation:
    """``CONVERSATION`` over one generation's orchestrator."""

    def __init__(
        self,
        orchestrator_factory: Callable[[], TurnOrchestrator],
        affection: AffectionGetter,
        reply_policy: ReplyPolicyGetter,
    ) -> None:
        self._orchestrator_factory = orchestrator_factory
        self._affection = affection
        self._reply_policy = reply_policy

    async def deliver_initiated_reply(self, reply: InitiatedReply) -> str:
        """Store ``reply`` on this generation and return its last message id."""
        with bound_turn_getters(self._affection, self._reply_policy):
            return await commit_initiated_reply(self._orchestrator_factory(), reply)
