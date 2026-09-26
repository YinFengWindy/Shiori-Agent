"""QQ account plugin: private external NapCat connections and account actions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator
from core.accounts.target_contract import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext

_UNRESOLVED_ENV_RE = re.compile(r"^\$\{\w+\}$")


class QQConfigModel(BaseModel):
    """``[plugins.qq]``：值明文存 TOML，支持 ``${ENV}`` 占位符。"""

    bot_uin: str = Field(
        default="",
        title="Bot QQ 号",
        description="NapCat 登录的机器人 QQ 号；留空则不启用 QQ 渠道。",
    )
    ws_uri: str = Field(
        default="",
        title="NapCat WebSocket 地址",
        description="如 ws://localhost:3001；留空沿用 NcatBot 默认值。",
    )
    ws_token: str = Field(
        default="",
        title="NapCat WebSocket 令牌",
        description="NapCat 正向 WebSocket 的 access token；留空沿用 NcatBot 默认值。",
    )
    websocket_open_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        title="连接超时",
        json_schema_extra={"unit": "秒"},
        description="与 NapCat 建立 WebSocket 连接的握手超时。",
    )

    @field_validator("bot_uin", "ws_uri", "ws_token", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> str:
        # 宿主已展开 ${ENV}；仍未展开说明变量缺失，按未填写处理。旧配置里的
        # bot_uin 可能是 TOML 整数，这里统一成字符串。
        text = str(value if value is not None else "").strip()
        return "" if _UNRESOLVED_ENV_RE.fullmatch(text) else text


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Migrates the old connection and contributes one multi-account channel."""
    from pathlib import Path

    from desktop_bridge.method_policy import Concurrency

    from .accounts_runtime import QQAccountsRuntime
    from .accounts_store import QQAccountsStore

    config = QQConfigModel.model_validate(ctx.config.as_dict())
    workspace = ctx.workspace
    if not isinstance(workspace, Path):
        raise RuntimeError("QQ 插件需要持久化 workspace")
    store = QQAccountsStore(workspace)
    store.migrate_legacy(
        bot_uin=config.bot_uin,
        ws_uri=config.ws_uri,
        ws_token=config.ws_token,
        timeout_seconds=config.websocket_open_timeout_seconds,
    )
    runtime = QQAccountsRuntime(store, ctx.accounts)
    ctx.channels.add(runtime)
    ctx.rpc.register(
        "accounts.settings",
        lambda payload: _settings(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.rpc.register("accounts.save", runtime.save_draft)
    ctx.rpc.register(
        "accounts.connect", lambda payload: runtime.connect_saved(str(payload["ref"]))
    )
    ctx.rpc.register(
        "accounts.disconnect", lambda payload: _disconnect(runtime, payload)
    )
    ctx.rpc.register(
        "accounts.disconnect_draft",
        lambda payload: _disconnect_draft(runtime, payload),
    )
    ctx.rpc.register("accounts.logout", lambda payload: _logout(runtime, payload))
    ctx.rpc.register(
        "accounts.managed_status",
        lambda payload: runtime.managed_status(str(payload["ref"])),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.rpc.register(
        "accounts.refresh_qrcode",
        lambda payload: runtime.refresh_qrcode(str(payload["ref"])),
    )
    ctx.rpc.register(
        "accounts.remove_draft", lambda payload: _remove_draft(runtime, payload)
    )
    ctx.rpc.register(
        "accounts.discover",
        lambda payload: _discover(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.rpc.register("accounts.send", lambda payload: _send(runtime, payload))
    ctx.rpc.register(
        ACCOUNT_TARGETS_METHOD,
        lambda payload: _discover(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.rpc.register(
        ACCOUNT_SEND_METHOD, lambda payload: _send_account(runtime, payload)
    )


async def _settings(runtime, payload: dict) -> dict:
    return runtime.settings(
        str(payload["account_id"]) if payload.get("account_id") else None,
        str(payload["ref"]) if payload.get("ref") else None,
    )


async def _disconnect(runtime, payload: dict) -> dict:
    await runtime.disconnect(str(payload["account_id"]))
    return {"ok": True}


async def _disconnect_draft(runtime, payload: dict) -> dict:
    await runtime.disconnect_draft(str(payload["ref"]))
    return {"ok": True}


async def _logout(runtime, payload: dict) -> dict:
    await runtime.logout(str(payload["account_id"]))
    return {"ok": True}


async def _remove_draft(runtime, payload: dict) -> dict:
    await runtime.remove_draft(str(payload["ref"]))
    return {"ok": True}


async def _discover(runtime, payload: dict) -> dict:
    return await runtime.discover(
        str(payload["account_id"]),
        str(payload["kind"]),
        str(payload.get("group_id") or ""),
    )


async def _send(runtime, payload: dict) -> dict:
    return await runtime.send_target(
        str(payload["account_id"]),
        str(payload["kind"]),
        str(payload["target_id"]),
        str(payload["message"]),
    )


async def _send_account(runtime, payload: dict) -> dict:
    """Translate the shared account request into QQ's native target operation."""
    if payload.get("message_thread_id") is not None:
        raise ValueError("QQ 不支持话题目标")
    return await _send(
        runtime,
        {
            "account_id": payload["account_id"],
            "kind": payload["target_kind"],
            "target_id": payload["target_id"],
            "message": payload["message"],
        },
    )
