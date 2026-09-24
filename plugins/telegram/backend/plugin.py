"""Telegram 渠道插件入口：校验配置，凭据齐备时贡献 Telegram 渠道（#363 T4）。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")


class TelegramConfigModel(BaseModel):
    """``[plugins.telegram]``：Bot token 明文存 TOML，支持 ``${ENV}`` 占位符。"""

    token: str = Field(
        default="",
        title="Bot Token",
        description="从 @BotFather 获取；留空则不启用 Telegram 渠道。",
    )

    @field_validator("token", mode="before")
    @classmethod
    def _normalize_token(cls, value: object) -> str:
        # 宿主已展开 ${ENV}；仍未展开说明变量缺失，按未配置处理。
        text = str(value or "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text


async def setup(ctx: "PluginRuntimeContext") -> None:
    """凭据齐备时贡献渠道；bot 命令在 start 时取自 ``ChannelContext``。"""
    config = TelegramConfigModel.model_validate(ctx.config.as_dict())
    if not config.token:
        return
    # 未配置时不导入 python-telegram-bot，保持内置时期「有 token 才加载」的启动开销。
    from .channel import TelegramChannel

    ctx.channels.add(TelegramChannel(token=config.token))
