"""Compose the channel group and account-scoped RPC surface."""

from shiori_sdk.accounts.targets import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD
from shiori_sdk.channels.context import ChannelPluginContext
from shiori_sdk.rpc import Concurrency

from .accounts import GrokAccounts
from .config import CHANNEL
from .delivery import GrokDelivery


async def setup(ctx: ChannelPluginContext) -> None:
    """Register independent saved role connections using the standard channel host."""
    group = ctx.channels.group(CHANNEL)
    ctx.channels.add(group)
    accounts = GrokAccounts(ctx, group)
    delivery = GrokDelivery(accounts)
    ctx.accounts.on_delete(accounts.delete_plan)
    ctx.accounts.on_rules_change(accounts.save_rules)
    ctx.rpc.register(
        "account.detail", accounts.detail, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register("account.save", accounts.save)
    ctx.rpc.register("account.disconnect", accounts.disconnect)
    ctx.rpc.register("account.reset_exchange", accounts.reset_exchange)
    ctx.rpc.register(
        ACCOUNT_TARGETS_METHOD, delivery.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register(ACCOUNT_SEND_METHOD, delivery.send)
    await accounts.load()
