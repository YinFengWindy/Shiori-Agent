"""QQ account plugin: private external NapCat connections and account actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.accounts import AccountDeletionPlan
from core.accounts.target_contract import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD

if TYPE_CHECKING:
    from agent.plugin_host.runtime_context import PluginRuntimeContext


async def setup(ctx: "PluginRuntimeContext") -> None:
    """Loads the plugin-owned accounts and contributes one multi-account channel."""
    from pathlib import Path

    from desktop_bridge.method_policy import Concurrency

    from .accounts_runtime import QQAccountsRuntime
    from .accounts_store import QQAccountsStore

    workspace = ctx.workspace
    if not isinstance(workspace, Path):
        raise RuntimeError("QQ 插件需要持久化 workspace")
    runtime = QQAccountsRuntime(QQAccountsStore(workspace), ctx.accounts)
    await runtime.load()
    ctx.channels.add(runtime)

    def delete_account(config_ref: str) -> AccountDeletionPlan:
        return AccountDeletionPlan(
            disconnect=lambda: runtime.disconnect_account(config_ref),
            purge=lambda: runtime.purge_account(config_ref),
        )

    ctx.accounts.on_delete(delete_account)
    ctx.accounts.on_rules_change(runtime.save_rules)
    ctx.rpc.register(
        "accounts.settings",
        lambda payload: _settings(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.rpc.register("accounts.save", runtime.save_draft)
    ctx.rpc.register("accounts.connect", lambda payload: _connect(runtime, payload))
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


async def _connect(runtime, payload: dict) -> dict:
    """Connects a saved draft only for the role that owns it."""
    from .accounts_settings import ensure_config_owner

    ref = str(payload["ref"])
    if ref not in runtime._configs:
        raise KeyError("QQ 配置引用不存在")
    ensure_config_owner(runtime._configs[ref], str(payload.get("role_id") or ""))
    return await runtime.connect_saved(ref)


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
