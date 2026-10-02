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
    """Registers a handler owned by the current plugin scope.

    ``admission_exempt`` keeps bounded control RPCs (such as dismissal) available
    while ordinary backend admission is paused for a settings transaction.
    """

    def register(
        self,
        name: str,
        handler: RpcHandler,
        *,
        concurrency: Concurrency = Concurrency.MUTATION,
        admission_exempt: bool = False,
    ) -> None: ...

    async def emit(self, name: str, payload: dict[str, object]) -> bool: ...


class PluginRpcError(RuntimeError):
    """A stable plugin-owned error code carried across the RPC boundary."""

    def __init__(
        self, code: str, message: str, *, details: dict[str, object] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.details = details
