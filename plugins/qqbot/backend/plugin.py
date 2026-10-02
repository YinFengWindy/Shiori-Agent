from __future__ import annotations

from typing import TYPE_CHECKING

from .account_channel import QQBotAccountsChannel
from shiori_sdk.accounts import (
    AccountDeletionPlan,
    AccountResponseRules,
    response_rules_to_dict,
)
from shiori_sdk.accounts.targets import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD
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

    store = QQBotAccountStore(ctx.kv)
    channel = QQBotAccountsChannel(ctx, store, ctx.manifest.channel_chat_types("qqbot"))
    ctx.channels.add(channel)

    def delete_account(config_ref: str) -> AccountDeletionPlan:
        app_id = _app_id(config_ref)
        return AccountDeletionPlan(
            disconnect=lambda: channel.disconnect_account(app_id),
            purge=lambda: channel.purge_account(app_id),
        )

    def save_rules(config_ref: str, rules: AccountResponseRules) -> None:
        store.set_rules(_app_id(config_ref), response_rules_to_dict(rules))

    ctx.accounts.on_delete(delete_account)
    ctx.accounts.on_rules_change(save_rules)
    ctx.rpc.register(
        "account.detail", channel.detail, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register(
        ACCOUNT_TARGETS_METHOD, channel.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register("account.save", channel.save_and_connect)
    ctx.rpc.register("account.disconnect", channel.disconnect)
    ctx.rpc.register(ACCOUNT_SEND_METHOD, channel.account_send)
