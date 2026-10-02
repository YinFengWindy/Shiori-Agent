"""Pet-owned surface dismissal over the existing plugin RPC transport."""

from typing import Any

from shiori_sdk.rpc import RpcCapability
from shiori_sdk.rpc import Concurrency


def register_bubble_rpc(rpc: RpcCapability) -> None:
    """Routes a dismissal to the pet background without a host-specific IPC channel."""

    async def dismiss(_payload: dict[str, Any]) -> dict[str, Any]:
        await rpc.emit("bubble.dismissed", {})
        return {"ok": True}

    rpc.register(
        "bubble.dismiss",
        dismiss,
        concurrency=Concurrency.READ_ONLY,
        admission_exempt=True,
    )
