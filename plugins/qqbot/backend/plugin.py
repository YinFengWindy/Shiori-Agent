from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, Field, field_validator

from .channel import QQBotChannel

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")


class QQBotGroupConfigModel(BaseModel):
    """Compatibility schema for the historical, currently disabled group mode."""

    group_openid: str = Field(
        default="",
        validation_alias=AliasChoices("group_openid", "groupOpenid"),
    )
    require_at: bool = Field(
        default=True,
        validation_alias=AliasChoices("require_at", "requireAt"),
    )
    allow_proactive: bool = Field(
        default=False,
        validation_alias=AliasChoices("allow_proactive", "allowProactive"),
    )


class QQBotConfigModel(BaseModel):
    """Configuration for the official QQBot application credentials."""

    app_id: str = Field(
        default="",
        title="App ID",
        validation_alias=AliasChoices("app_id", "appId"),
    )
    client_secret: str = Field(
        default="",
        title="App Secret",
        validation_alias=AliasChoices("client_secret", "clientSecret"),
    )
    groups: list[QQBotGroupConfigModel] = Field(
        default_factory=list, title="群聊（旧版）"
    )

    @field_validator("app_id", "client_secret", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str:
        text = str(value or "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text


async def setup(ctx: "PluginRuntimeContext") -> None:
    """校验配置，凭据齐备时贡献 QQBot 渠道；校验失败由内核回滚。"""
    config = QQBotConfigModel.model_validate(ctx.config.as_dict())
    if not config.app_id or not config.client_secret:
        return
    ctx.channels.add(
        QQBotChannel(
            app_id=config.app_id,
            client_secret=config.client_secret,
            groups=config.groups,
            chat_types=ctx.manifest.channel_chat_types("qqbot"),
        )
    )
