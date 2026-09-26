"""Telegram 渠道插件入口：校验配置，凭据齐备时贡献 Telegram 渠道（#363 T4）。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")


class TelegramBotConfig(BaseModel):
    """A stable plugin-private Bot reference and its credential."""

    ref: str
    token: str
    enabled: bool = True

    @field_validator("ref")
    @classmethod
    def _valid_ref(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9_]{1,48}", value):
            raise ValueError("Bot ref must be a lowercase portable identifier")
        return value

    @field_validator("token", mode="before")
    @classmethod
    def _normalize_token(cls, value: object) -> str:
        return str(value or "").strip()


class TelegramConfigModel(BaseModel):
    """``[plugins.telegram]``：Bot token 明文存 TOML，支持 ``${ENV}`` 占位符。"""

    token: str = Field(
        default="",
        title="Bot Token",
        description="从 @BotFather 获取；留空则不启用 Telegram 渠道。",
    )
    bots: list[TelegramBotConfig] = Field(default_factory=list)

    @field_validator("token", mode="before")
    @classmethod
    def _normalize_token(cls, value: object) -> str:
        # 宿主已展开 ${ENV}；仍未展开说明变量缺失，按未配置处理。
        text = str(value or "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text

    @property
    def configured_bots(self) -> list[TelegramBotConfig]:
        """Reads the old single Token as the stable legacy account."""
        bots = list(self.bots)
        if self.token and not any(bot.ref == "legacy" for bot in bots):
            bots.insert(0, TelegramBotConfig(ref="legacy", token=self.token))
        refs = [bot.ref for bot in bots]
        if len(refs) != len(set(refs)):
            raise ValueError("Duplicate Telegram Bot reference")
        return bots


async def setup(ctx: "PluginRuntimeContext") -> None:
    """凭据齐备时贡献渠道；bot 命令在 start 时取自 ``ChannelContext``。"""
    config = TelegramConfigModel.model_validate(ctx.config.as_dict())
    from .account_api import TelegramAccountApi

    channels = {}
    configured_bots = config.configured_bots
    for bot in configured_bots:
        if not bot.enabled or not bot.token or _UNRESOLVED_ENV_RE.fullmatch(bot.token):
            continue
        from .channel import TelegramChannel
        from telegram.error import InvalidToken

        channel_name = "telegram" if bot.ref == "legacy" else f"telegram_{bot.ref}"
        try:
            channel = TelegramChannel(
                token=bot.token,
                name=channel_name,
                config_ref=bot.ref,
                accounts=ctx.accounts,
                known_store=ctx.kv,
                chat_types=ctx.manifest.channel_chat_types(channel_name),
            )
        except InvalidToken:
            candidate_id = bot.token.split(":", 1)[0]
            if candidate_id.isdigit():
                account = ctx.accounts.register(
                    platform="telegram",
                    platform_account_id=candidate_id,
                    config_ref=bot.ref,
                )
                ctx.accounts.report(
                    account.record.id,
                    connection="login_required",
                    error="Invalid Bot Token",
                )
            continue
        account = ctx.accounts.register(
            platform="telegram",
            platform_account_id=bot.token.split(":", 1)[0],
            config_ref=bot.ref,
        )
        channel._account_id = account.record.id
        channels[bot.ref] = channel
        ctx.channels.add(channel)
    TelegramAccountApi(channels, ctx.rpc, ctx.kv).register()
