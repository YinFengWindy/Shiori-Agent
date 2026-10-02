"""Plugin RPC registration and concurrency values."""

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Protocol


class Concurrency(Enum):
    """Which dispatcher lane runs the request."""

    READ_ONLY = "read_only"
    INTEGRATION = "integration"
    MUTATION = "mutation"
    # The settings transaction owns its serial lock; scheduling it through a
    # shared lane would starve health checks and cancellation while it drains.
    SETTINGS_APPLY = "settings_apply"
    # Renderer rendezvous must leave capacity for callback RPCs and their replies.
    PLUGIN_TRANSPORT = "plugin_transport"


type RpcHandler = Callable[[dict[str, object]], Awaitable[dict[str, object] | None]]


class RpcCapability(Protocol):
    """Registers a handler owned by the current plugin scope."""

    def register(
        self,
        name: str,
        handler: RpcHandler,
        *,
        concurrency: Concurrency = Concurrency.MUTATION,
    ) -> None: ...
