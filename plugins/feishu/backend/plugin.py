"""Feishu/Lark plugin entry: compose account lifecycle and delivery RPCs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.accounts.target_contract import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD
from infra.channels.account_group import AccountChannelGroup

from .account_delivery import FeishuAccountDelivery
from .accounts import FeishuAccounts
from .config import FeishuAppConfig
from .formatting import CHANNEL

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Registers saved applications and the RPCs that manage them."""
    from desktop_bridge.method_policy import Concurrency

    group = AccountChannelGroup(CHANNEL)
    ctx.channels.add(group)
    accounts = FeishuAccounts(ctx, group)
    delivery = FeishuAccountDelivery(ctx, accounts)

    async def verify(payload: dict[str, Any]) -> dict[str, object]:
        identity = await accounts.verify(FeishuAppConfig.model_validate(payload))
        return {"name": identity["name"], "open_id": identity["open_id"]}

    ctx.rpc.register(
        "accounts.profile", delivery.profile, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register(
        ACCOUNT_TARGETS_METHOD, delivery.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register("accounts.send", delivery.send)
    ctx.rpc.register(ACCOUNT_SEND_METHOD, delivery.send_account)
    ctx.rpc.register("accounts.verify", verify, concurrency=Concurrency.INTEGRATION)
    ctx.rpc.register("accounts.save", accounts.save)
    ctx.rpc.register("accounts.disconnect", accounts.disconnect)
    ctx.accounts.on_delete(accounts.delete_plan)
    ctx.accounts.on_rules_change(accounts.save_rules)
    await accounts.load()
