"""Host side of the ``external_turns`` capability (#721).

A plugin-submitted message is routed exactly like a group message a channel
account admitted (``core.channels.role_routing``) and runs through
``AgentLoop.process_external_turn``: never queued behind other role work,
never dispatched to a channel. Routing happens only once the role's turn gate
is held, so a busy role leaves no trace of the submission.

The submitting plugin is trusted to speak for the role it names, as with any
plugin capability; the host only checks that the role exists and that the
platform is not the desktop or a channel the host runs, so a plugin cannot
write into another transport's conversations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.channels.role_routing import CONVERSATION_DUPLICATE_KEY, RoleTurnRouter
from core.common.channel_directory import ChannelDirectory
from core.roles.errors import RoleNotFoundError
from core.roles.role_runtime import RoleExecutionContext
from shiori_sdk.channels.chat_types import CHAT_TYPE_GROUP
from shiori_sdk.channels.message_source import GROUP_NAME_KEY, SENDER_NAME_KEY
from shiori_sdk.external_turns import ExternalTurnMessage, ExternalTurnResult
from shiori_sdk.messages import InboundMessage

# Role execution source of plugin-submitted turns (channel accounts use
# ``role_account``).
EXTERNAL_TURN_SOURCE = "external_turn"

# Routes the turn once the gate is held; None when it is a duplicate.
type ExternalTurnAdmission = Callable[[], InboundMessage | None]
# ``AgentLoop.process_external_turn``.
type ExternalTurnRunner = Callable[
    [RoleExecutionContext, ExternalTurnAdmission], Awaitable[ExternalTurnResult]
]


class HostExternalTurns:
    """Routes submitted messages as group-chat turns and runs them at once."""

    def __init__(
        self,
        router: RoleTurnRouter,
        run_turn: ExternalTurnRunner,
        *,
        channel_directory: ChannelDirectory,
    ) -> None:
        self._router = router
        self._run_turn = run_turn
        self._channels = channel_directory

    async def submit(self, message: ExternalTurnMessage) -> ExternalTurnResult:
        """Runs ``message`` as an external-context turn of its role.

        The conversation is a group chat named by its title, so the turn is
        judged external and the sender is never the bound user. Nothing is
        routed or stored unless the role's turn gate is taken; a message ID
        the conversation already holds runs nothing.
        """
        if self._channels.serves(message.platform):
            raise ValueError(f"外部回合不能使用宿主渠道名: {message.platform}")
        metadata: dict[str, object] = {
            "chat_type": CHAT_TYPE_GROUP,
            GROUP_NAME_KEY: message.conversation_title,
            SENDER_NAME_KEY: message.sender_name,
            "external_message_id": message.message_id,
            "source": EXTERNAL_TURN_SOURCE,
        }
        inbound = InboundMessage(
            channel=message.platform,
            sender=message.sender_id,
            chat_id=message.conversation_id,
            content=message.text,
            metadata=metadata,
        )
        try:
            context = self._router.network_turn_context(
                inbound, message.role_id, source=EXTERNAL_TURN_SOURCE
            )
        except RoleNotFoundError as error:
            raise ValueError(f"角色不存在: {message.role_id}") from error

        def admit() -> InboundMessage | None:
            routed = self._router.route(
                inbound, message.role_id, metadata, context=context
            )
            return None if routed.metadata.get(CONVERSATION_DUPLICATE_KEY) else routed

        return await self._run_turn(context, admit)
