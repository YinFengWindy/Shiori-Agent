from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_validator

from .channel import FeishuChannel
from .formatting import DOMAINS, FEISHU_DOMAIN, LARK_DOMAIN

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")
# The removed first implementation stored the API base URL itself.
_DOMAIN_ALIASES = {FEISHU_DOMAIN: "feishu", LARK_DOMAIN: "lark"}


class FeishuConfigModel(BaseModel):
    """Credentials of a Feishu / Lark custom app (企业自建应用) with a bot."""

    app_id: str = Field(
        default="",
        title="App ID",
        description="开发者后台「凭证与基础信息」里的 App ID（cli_…）",
    )
    app_secret: str = Field(
        default="",
        title="App Secret",
        description="同一页面的 App Secret，支持 ${ENV} 引用环境变量",
    )
    domain: Literal["feishu", "lark"] = Field(
        default="feishu",
        title="服务域名",
        description="feishu：飞书（open.feishu.cn）；lark：Lark 国际版（open.larksuite.com）",
    )

    @field_validator("app_id", "app_secret", mode="before")
    @classmethod
    def _normalize_credential(cls, value: object) -> str:
        text = str(value or "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text

    @field_validator("domain", mode="before")
    @classmethod
    def _normalize_domain(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip().rstrip("/")
            return _DOMAIN_ALIASES.get(text, text.lower() or "feishu")
        return value

    @property
    def base_url(self) -> str:
        return DOMAINS[self.domain]


async def setup(ctx: "PluginRuntimeContext") -> None:
    """校验配置，凭据齐备时贡献飞书渠道；校验失败由内核回滚。"""
    config = FeishuConfigModel.model_validate(ctx.config.as_dict())
    if not config.app_id or not config.app_secret:
        return
    ctx.channels.add(
        FeishuChannel(
            app_id=config.app_id,
            app_secret=config.app_secret,
            domain=config.base_url,
        )
    )
