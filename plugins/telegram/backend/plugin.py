"""Telegram 渠道插件入口：Bot 账号存在插件自己的存储里，按需连接（#450）。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from shiori_sdk.core.services import ACCOUNTS, CHANNELS, KV, RPC

if TYPE_CHECKING:
    from shiori_sdk.channels.context import ChannelPluginContext


async def setup(ctx: "ChannelPluginContext") -> None:
    """Registers saved Bots and the RPCs that add, connect and remove them."""
    from .account_api import TelegramAccountApi
    from .bots import TelegramBots
    from .credentials import TelegramBotStore

    group = ctx.require(CHANNELS).group("telegram")
    ctx.require(CHANNELS).add(group)
    bots = TelegramBots(ctx, TelegramBotStore(ctx.require(KV)), group)
    await bots.load()
    TelegramAccountApi(bots, ctx.require(RPC), ctx.require(KV)).register()
    ctx.require(RPC).register("bot.save", bots.save)
    ctx.require(RPC).register("bot.disconnect", bots.disconnect)
    ctx.require(ACCOUNTS).on_delete(bots.delete_plan)
    ctx.require(ACCOUNTS).on_rules_change(bots.save_rules)
