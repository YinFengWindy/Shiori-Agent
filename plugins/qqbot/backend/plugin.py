from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import AliasChoices, BaseModel, Field, field_validator

from .account_channel import QQBotAccountsChannel
from core.accounts import AccountDeletionPlan
from core.accounts.target_contract import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD
from .accounts import QQBotAccountStore

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

# Host settings keys (with aliases) of the former single application.
_LEGACY_KEYS = frozenset({"app_id", "appId", "client_secret", "clientSecret"})
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

    def delete_account(config_ref: str) -> AccountDeletionPlan:
        if not config_ref.startswith("app:"):
            raise ValueError(f"QQBot 账号引用无效: {config_ref}")
        app_id = config_ref.removeprefix("app:")
        # The legacy application is re-imported from host settings on every
        # setup, so its credential must leave config.toml as well. ``config``
        # holds expanded values, so an ``${ENV}`` App ID still matches.
        return AccountDeletionPlan(
            disconnect=lambda: channel.disconnect_account(app_id),
            purge=lambda: channel.purge_account(app_id),
            plugin_config=(
                {key: value for key, value in raw.items() if key not in _LEGACY_KEYS}
                if config.app_id == app_id
                else None
            ),
        )

    ctx.accounts.on_delete(delete_account)
    ctx.rpc.register(
        "account.detail", channel.detail, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register(
        ACCOUNT_TARGETS_METHOD, channel.targets, concurrency=Concurrency.READ_ONLY
    )
    ctx.rpc.register("account.save", channel.save_and_connect)
    ctx.rpc.register("account.disconnect", channel.disconnect)
    ctx.rpc.register(ACCOUNT_SEND_METHOD, channel.account_send)
