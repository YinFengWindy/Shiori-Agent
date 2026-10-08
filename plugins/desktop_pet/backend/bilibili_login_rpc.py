"""``plugin.desktop_pet.bilibili.*`` RPCs for the pet role's Bilibili login.

There is deliberately no method that accepts cookies: QR login is the only way
credentials enter the plugin.
"""

from __future__ import annotations

from shiori_sdk.rpc import Concurrency, RpcCapability

from .bilibili_login import BilibiliLoginService
from .rpc import require_role_id


def register_bilibili_login(rpc: RpcCapability, service: BilibiliLoginService) -> None:
    """Expose QR login, account status and logout keyed by ``role_id``."""

    async def start(payload: dict[str, object]) -> dict[str, object]:
        return await service.start(require_role_id(payload))

    async def poll(payload: dict[str, object]) -> dict[str, object]:
        return await service.poll(require_role_id(payload))

    async def status(payload: dict[str, object]) -> dict[str, object]:
        return await service.status(require_role_id(payload))

    async def logout(payload: dict[str, object]) -> dict[str, object]:
        return service.logout(require_role_id(payload))

    # The first three wait on Bilibili, so they run in the integration lane.
    rpc.register("bilibili.login.start", start, concurrency=Concurrency.INTEGRATION)
    rpc.register("bilibili.login.poll", poll, concurrency=Concurrency.INTEGRATION)
    rpc.register("bilibili.account.status", status, concurrency=Concurrency.INTEGRATION)
    rpc.register("bilibili.account.logout", logout)
