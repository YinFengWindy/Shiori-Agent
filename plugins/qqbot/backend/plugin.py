from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, Field, field_validator

from .account_channel import QQBotAccountsChannel
from .accounts import QQBotAccountStore

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")


class QQBotConfigModel(BaseModel):
    """Legacy single-application credentials accepted during migration."""

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

    @field_validator("app_id", "client_secret", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str:
        text = str(value or "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Migrate legacy credentials and contribute one multi-application channel."""
    from desktop_bridge.method_policy import Concurrency

    config = QQBotConfigModel.model_validate(ctx.config.as_dict())
    store = QQBotAccountStore(ctx.kv)
    raw = ctx.config.raw_as_dict()
    raw_secret = raw.get("client_secret", raw.get("clientSecret"))
    store.migrate_legacy(
        config.app_id,
        str(raw_secret).strip() if raw_secret else config.client_secret,
    )
    channel = QQBotAccountsChannel(ctx, store, ctx.manifest.channel_chat_types("qqbot"))
    ctx.channels.add(channel)
    ctx.rpc.register(
        "account.detail", channel.detail, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register(
        "account.targets", channel.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register("account.save", channel.save_and_connect)
    ctx.rpc.register("account.disconnect", channel.disconnect)
    ctx.rpc.register("account.send", channel.send_target)
