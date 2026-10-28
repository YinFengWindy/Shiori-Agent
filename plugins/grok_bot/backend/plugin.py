"""Compose the channel group and account-scoped RPC surface."""

from shiori_sdk.accounts.targets import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD
from shiori_sdk.accounts.routing import ACCOUNT_RESOLVE_METHOD
from shiori_sdk.runtime import PluginRuntimeContext
from shiori_sdk.rpc import Concurrency
from shiori_sdk.core.services import ACCOUNTS, CHANNELS, RPC

from .accounts import GrokAccounts
from .config import CHANNEL
from .delivery import GrokDelivery


async def setup(ctx: PluginRuntimeContext) -> None:
    """Register independent saved role connections using the standard channel host."""
    group = ctx.require(CHANNELS).group(CHANNEL)
    ctx.require(CHANNELS).add(group)
    accounts = GrokAccounts(ctx, group)
    delivery = GrokDelivery(accounts)
    ctx.require(ACCOUNTS).on_delete(accounts.delete_plan)
    ctx.require(ACCOUNTS).on_rules_change(accounts.save_rules)
    ctx.require(RPC).register(
        "account.detail", accounts.detail, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register("account.save", accounts.save)
    ctx.require(RPC).register("account.disconnect", accounts.disconnect)
    ctx.require(RPC).register(
        ACCOUNT_TARGETS_METHOD, delivery.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register(ACCOUNT_SEND_METHOD, delivery.send)
    ctx.require(RPC).register(
        ACCOUNT_RESOLVE_METHOD, delivery.resolve, concurrency=Concurrency.READ_ONLY
    )
    await accounts.load()
