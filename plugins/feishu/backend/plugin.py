"""Feishu/Lark plugin entry: compose account lifecycle and delivery RPCs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shiori_sdk.accounts.targets import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD
from shiori_sdk.accounts.routing import ACCOUNT_RESOLVE_METHOD
from shiori_sdk.core.services import ACCOUNTS, CHANNELS, RPC

from .account_delivery import FeishuAccountDelivery
from .accounts import FeishuAccounts
from .config import FeishuAppConfig
from .formatting import CHANNEL

if TYPE_CHECKING:
    from shiori_sdk.runtime import PluginRuntimeContext


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Registers saved applications and the RPCs that manage them."""
    from shiori_sdk.rpc import Concurrency

    group = ctx.require(CHANNELS).group(CHANNEL)
    ctx.require(CHANNELS).add(group)
    accounts = FeishuAccounts(ctx, group)
    delivery = FeishuAccountDelivery(ctx, accounts)

    async def verify(payload: dict[str, Any]) -> dict[str, object]:
        identity = await accounts.verify(FeishuAppConfig.model_validate(payload))
        return {"name": identity["name"], "open_id": identity["open_id"]}

    ctx.require(RPC).register(
        "accounts.profile", delivery.profile, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register(
        ACCOUNT_TARGETS_METHOD, delivery.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register("accounts.send", delivery.send)
    ctx.require(RPC).register(ACCOUNT_SEND_METHOD, delivery.send_account)
    ctx.require(RPC).register(
        ACCOUNT_RESOLVE_METHOD,
        delivery.resolve_account,
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.require(RPC).register(
        "accounts.verify", verify, concurrency=Concurrency.INTEGRATION
    )
    ctx.require(RPC).register("accounts.save", accounts.save)
    ctx.require(RPC).register("accounts.disconnect", accounts.disconnect)
    ctx.require(ACCOUNTS).on_delete(accounts.delete_plan)
    ctx.require(ACCOUNTS).on_rules_change(accounts.save_rules)
    await accounts.load()
