"""Host side of the ``external_turns`` capability (#721).

A plugin-submitted message is routed exactly like a group message a channel
account admitted (``core.channels.role_routing``) and runs through
``AgentLoop.process_external_turn``: never queued behind other role work,
never dispatched to a channel.

The submitting plugin is trusted to speak for the role it names, as with any
plugin capability; the host only checks that the role exists and that the
platform is not the desktop or a channel the host runs, so a plugin cannot
write into another transport's conversations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.channels.role_routing import CONVERSATION_DUPLICATE_KEY, RoleTurnRouter
from core.common.channel_directory import ChannelDirectory
from core.roles.store import RoleStore
from shiori_sdk.channels.chat_types import CHAT_TYPE_GROUP
from shiori_sdk.channels.message_source import GROUP_NAME_KEY, SENDER_NAME_KEY
from shiori_sdk.external_turns import (
    ExternalTurnMessage,
    ExternalTurnResult,
    ExternalTurns,
)
from shiori_sdk.messages import InboundMessage

# Role execution source of plugin-submitted turns (channel accounts use
# ``role_account``).
EXTERNAL_TURN_SOURCE = "external_turn"

# Runs a routed turn; None when the role was busy (``process_external_turn``).
type ExternalTurnRunner = Callable[[InboundMessage], Awaitable[str | None]]


class HostExternalTurns:
    """Routes submitted messages as group-chat turns and runs them at once."""

    def __init__(
        self,
        router: RoleTurnRouter,
        run_turn: ExternalTurnRunner,
        *,
        role_store: RoleStore,
        channel_directory: ChannelDirectory,
    ) -> None:
        self._router = router
        self._run_turn = run_turn
        self._roles = role_store
        self._channels = channel_directory

    async def submit(self, message: ExternalTurnMessage) -> ExternalTurnResult:
        """Runs ``message`` as an external-context turn of its role.

        The conversation is a group chat named by its title, so the turn is
        judged external and the sender is never the bound user. A message ID
        the conversation already holds runs nothing.
        """
        if self._roles.get_role(message.role_id) is None:
            raise ValueError(f"角色不存在: {message.role_id}")
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
        routed = self._router.route(inbound, message.role_id, metadata)
        if routed.metadata.get(CONVERSATION_DUPLICATE_KEY):
            return ExternalTurnResult("duplicate")
        reply = await self._run_turn(routed)
        if reply is None:
            return ExternalTurnResult("busy")
        return ExternalTurnResult("replied", reply)

    def as_capability(self) -> ExternalTurns:
        """Checks the host implementation against the plugin contract."""
        return self
