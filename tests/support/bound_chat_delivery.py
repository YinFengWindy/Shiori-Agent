"""Proactive delivery to a bound private chat, faked for orchestrator tests.

Every external default proactive target is a private chat with the bound user
and is delivered through the role's account. Tests that only need *some*
external target build their ``TurnOrchestrator`` with
``bound_chat_orchestrator`` so the text reaches their own ``deliver`` probe.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from agent.account_delivery.service import AccountSendReceipt
from agent.looping.ports import SessionServices
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import OutboundPort
from bus.event_bus import EventBus
from shiori_sdk.accounts.targets import AccountTarget

# The platform user ID every faked bound chat reaches.
BOUND_USER_ID = "bound-user"


class FakeBoundChatDelivery:
    """Account delivery whose platform is ``deliver(content)``.

    A truthy result is a platform receipt; a falsy one is a refused send and
    raises, as a real plugin does. ``targets`` records every resolved chat.
    """

    def __init__(self, deliver: Callable[[str], Awaitable[object]]) -> None:
        self._deliver = deliver
        self.targets: list[tuple[str, str, str]] = []

    def bound_chat_target(
        self, role_id: str, channel: str, chat_id: str
    ) -> tuple[str, AccountTarget]:
        """Resolves any external chat to the bound user on its channel."""
        self.targets.append((role_id, channel, chat_id))
        return channel, AccountTarget("private", BOUND_USER_ID)

    async def send(
        self,
        channel: str,
        role_id: str,
        target: AccountTarget,
        message: str,
        *,
        source: str,
        media: list[str] | None = None,
    ) -> AccountSendReceipt:
        """Hands the text to ``deliver`` and returns a sent receipt."""
        if not await self._deliver(message):
            raise RuntimeError("平台拒绝发送")
        return AccountSendReceipt(
            attempt_id=f"attempt-{len(self.targets)}",
            account_id=f"{channel}:bot",
            channel=channel,
            target_kind=target.kind,
            target_id=target.id,
            platform_message_id="platform-1",
            ownership_current=True,
        )


def bound_chat_orchestrator(
    session: SessionServices,
    outbound: OutboundPort,
    *,
    deliver: Callable[[str], Awaitable[object]],
    event_bus: EventBus | None = None,
) -> tuple[TurnOrchestrator, FakeBoundChatDelivery]:
    """An orchestrator that sends external targets through ``deliver``.

    ``outbound`` still serves desktop targets.
    """
    delivery = FakeBoundChatDelivery(deliver)
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=session,
            outbound=outbound,
            event_bus=event_bus,
            account_delivery=cast(Any, delivery),
            bound_chat_target=delivery.bound_chat_target,
        )
    )
    return orchestrator, delivery
