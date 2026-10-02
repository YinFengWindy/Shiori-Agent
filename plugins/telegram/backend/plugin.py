"""Telegram 渠道插件入口：Bot 账号存在插件自己的存储里，按需连接（#450）。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shiori_sdk.channels.context import ChannelPluginContext


async def setup(ctx: "ChannelPluginContext") -> None:
    """Registers saved Bots and the RPCs that add, connect and remove them."""
    from .account_api import TelegramAccountApi
    from .bots import TelegramBots
    from .credentials import TelegramBotStore

    group = ctx.channels.group("telegram")
    ctx.channels.add(group)
    bots = TelegramBots(ctx, TelegramBotStore(ctx.kv), group)
    await bots.load()
    TelegramAccountApi(bots, ctx.rpc, ctx.kv).register()
    ctx.rpc.register("bot.save", bots.save)
    ctx.rpc.register("bot.disconnect", bots.disconnect)
    ctx.accounts.on_delete(bots.delete_plan)
    ctx.accounts.on_rules_change(bots.save_rules)
