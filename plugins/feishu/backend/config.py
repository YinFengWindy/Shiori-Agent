"""Feishu application configuration and legacy single-app migration."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .formatting import DOMAINS, FEISHU_DOMAIN, LARK_DOMAIN

UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")
_DOMAIN_ALIASES = {FEISHU_DOMAIN: "feishu", LARK_DOMAIN: "lark"}


class FeishuAppConfig(BaseModel):
    """One isolated custom bot application and its regional credential."""

    app_id: str
    app_secret: str
    domain: Literal["feishu", "lark"] = "feishu"

    @field_validator("app_id", "app_secret", mode="before")
    @classmethod
    def _normalize_credential(cls, value: object) -> str:
        text = str(value or "").strip()
        return "" if UNRESOLVED_ENV_RE.fullmatch(text) else text

    @field_validator("domain", mode="before")
    @classmethod
    def _normalize_domain(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip().rstrip("/")
            return _DOMAIN_ALIASES.get(text, text.lower() or "feishu")
        return value

    @property
    def ref(self) -> str:
        """Stable regional application reference used by the host account record."""
        return f"{self.domain}:{self.app_id}"

    @property
    def base_url(self) -> str:
        """Regional OpenAPI endpoint."""
        return DOMAINS[self.domain]


class FeishuAccountConfig(FeishuAppConfig):
    """Persisted connection intent for one configured application."""

    connection_enabled: bool = True
    connection_revision: int = Field(default=0, ge=0)


class FeishuConfigModel(FeishuAppConfig):
    """Application list plus the old single-app fields retained for migration."""

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
    accounts: list[FeishuAccountConfig] = Field(default_factory=list)
    legacy_channel_ref: str = ""

    @model_validator(mode="after")
    def _unique_accounts(self) -> "FeishuConfigModel":
        if any(not account.app_id for account in self.accounts):
            raise ValueError("飞书应用账号需要 App ID")
        refs = [account.ref for account in self.accounts]
        if len(refs) != len(set(refs)):
            raise ValueError("飞书应用的区域和 App ID 不得重复")
        return self

    @property
    def applications(self) -> list[FeishuAccountConfig]:
        """Includes the old app once until a settings save migrates it."""
        accounts = list(self.accounts)
        if self.app_id and not any(account.ref == self.ref for account in accounts):
            accounts.insert(
                0,
                FeishuAccountConfig(
                    app_id=self.app_id,
                    app_secret=self.app_secret,
                    domain=self.domain,
                ),
            )
        return [account for account in accounts if account.app_id]

    @property
    def channel_alias_ref(self) -> str:
        """Keeps the old bare channel bound to its original application."""
        return self.legacy_channel_ref or (self.ref if self.app_id else "")
