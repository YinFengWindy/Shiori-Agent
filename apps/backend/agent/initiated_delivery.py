"""``CONVERSATION`` for one runtime generation.

The orchestrator is built per delivery, for the role that owns the reply's
session, not when the generation is assembled: account sending is registered
after the plugin kernel is given this object.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from agent.looping.ports import SessionServices
from agent.tools.account_delivery import shared_account_delivery
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import PushToolOutboundPort
from bus.event_bus import EventBus
from conversation.initiated import bound_turn_getters, commit_initiated_reply
from conversation.service import ConversationService
from core.roles.affection_access import AffectionGetter
from core.roles.bound_chats import bound_chat_target
from core.roles.reply_policy import ReplyPolicyGetter
from core.roles.services import RoleSessionService
from core.roles.store import RoleStore
from session.manager import SessionManager
from session.manager.helpers import role_id_from_session_key
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from shiori_sdk.core.sessions import Presence


def orchestrator_for(
    role_id: str,
    *,
    session_manager: SessionManager,
    presence: Presence | None,
    push_tool: MessagePushTool,
    event_bus: EventBus | None,
    tools: ToolRegistry,
    role_store: RoleStore,
) -> TurnOrchestrator:
    """The delivery wiring a proactive loop uses, for one role's reply.

    The outbound port carries ``role_id``, so ``message_push`` refuses a desktop
    chat that is not the role's own, as it does for the proactive loop.
    """
    return TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=session_manager,
                presence=presence,
                conversation_service=ConversationService(session_manager),
            ),
            outbound=PushToolOutboundPort(
                push_tool, execution_context={"role_id": role_id}
            ),
            event_bus=event_bus,
            account_delivery=shared_account_delivery(tools),
            bound_chat_target=partial(bound_chat_target, role_store),
            role_lookup=role_store.get_role,
        )
    )


class HostConversation:
    """``CONVERSATION`` over one generation's orchestrators."""

    def __init__(
        self,
        orchestrator_for_role: Callable[[str], TurnOrchestrator],
        *,
        role_store: RoleStore,
        session_manager: SessionManager,
        affection: AffectionGetter,
        reply_policy: ReplyPolicyGetter,
    ) -> None:
        self._orchestrator_for_role = orchestrator_for_role
        self._role_store = role_store
        self._session_manager = session_manager
        self._affection = affection
        self._reply_policy = reply_policy

    async def deliver_initiated_reply(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Deliver ``reply`` for the role owning its session, on this generation."""
        role_id = role_id_from_session_key(reply.session_key)
        if not role_id:
            raise ValueError(f"主动投递只接受角色会话: {reply.session_key}")
        # Checked before the orchestrator opens the session, so a deleted
        # role's session is not recreated. Opening it by the role keeps the
        # session's role metadata current, as a proactive tick does.
        role = self._role_store.get_role(role_id)
        if role is None:
            raise ValueError(f"主动投递的角色不存在: {role_id}")
        RoleSessionService(self._session_manager).open_by_role(role)
        with bound_turn_getters(self._affection, self._reply_policy):
            return await commit_initiated_reply(
                self._orchestrator_for_role(role_id), reply
            )
