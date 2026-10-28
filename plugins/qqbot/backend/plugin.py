from __future__ import annotations

from typing import TYPE_CHECKING

from .account_channel import QQBotAccountsChannel
from shiori_sdk.accounts import (
    AccountDeletionPlan,
    AccountResponseRules,
    response_rules_to_dict,
)
from shiori_sdk.accounts.targets import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD
from shiori_sdk.accounts.routing import ACCOUNT_RESOLVE_METHOD
from shiori_sdk.core.services import ACCOUNTS, CHANNELS, KV, RPC
from .accounts import QQBotAccountStore

if TYPE_CHECKING:
    from shiori_sdk.channels.context import ChannelPluginContext


def _app_id(config_ref: str) -> str:
    if not config_ref.startswith("app:"):
        raise ValueError(f"QQBot 账号引用无效: {config_ref}")
    return config_ref.removeprefix("app:")


async def setup(ctx: "ChannelPluginContext") -> None:
    """Contribute one multi-application channel over the plugin-owned accounts."""
    from shiori_sdk.rpc import Concurrency

    store = QQBotAccountStore(ctx.require(KV))
    channel = QQBotAccountsChannel(ctx, store, ctx.manifest.channel_chat_types("qqbot"))
    ctx.require(CHANNELS).add(channel)

    def delete_account(config_ref: str) -> AccountDeletionPlan:
        app_id = _app_id(config_ref)
        return AccountDeletionPlan(
            disconnect=lambda: channel.disconnect_account(app_id),
            purge=lambda: channel.purge_account(app_id),
        )

    def save_rules(config_ref: str, rules: AccountResponseRules) -> None:
        store.set_rules(_app_id(config_ref), response_rules_to_dict(rules))

    ctx.require(ACCOUNTS).on_delete(delete_account)
    ctx.require(ACCOUNTS).on_rules_change(save_rules)
    ctx.require(RPC).register(
        "account.detail", channel.detail, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register(
        ACCOUNT_TARGETS_METHOD, channel.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.require(RPC).register("account.save", channel.save_and_connect)
    ctx.require(RPC).register("account.disconnect", channel.disconnect)
    ctx.require(RPC).register(ACCOUNT_SEND_METHOD, channel.account_send)
    ctx.require(RPC).register(
        ACCOUNT_RESOLVE_METHOD,
        channel.account_resolve,
        concurrency=Concurrency.READ_ONLY,
    )
