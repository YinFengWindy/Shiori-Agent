"""Identity pairing codes sent to a role account in a private chat.

Each channel plugin hands its private inbound messages here before routing
them to the role, stating the scope of its platform user IDs. A message that
is the pending pairing code binds the sender, gets a short confirmation from
the account and never reaches the role.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from bus.events import InboundMessage
from core.identity import IdentityScope

from .hub import ChannelHub

PAIRING_CONFIRMATION = "已绑定"


async def answer_pairing_code(
    hub: ChannelHub | None,
    message: InboundMessage,
    *,
    scope: IdentityScope,
    send: Callable[[str], Awaitable[object]],
) -> bool:
    """Binds and confirms through ``send`` when ``message`` is the pairing code.

    ``message`` must be a private chat message carrying its receiving
    ``account_id``; its ``sender`` is the platform user ID being bound.
    Returns True when the message was consumed and must be dropped. Without a
    hub (a channel driven outside the host) nothing is paired.
    """
    if hub is None or not hub.claim_pairing(message, scope=scope):
        return False
    await send(PAIRING_CONFIRMATION)
    return True
