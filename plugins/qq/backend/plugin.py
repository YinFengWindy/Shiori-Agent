"""QQ account plugin: private managed NapCat instances and account actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shiori_sdk.accounts import VIA_ACCOUNT_KEY, AccountDeletionPlan
from shiori_sdk.accounts.routing import AccountRoute
from shiori_sdk.accounts.routing import ACCOUNT_RESOLVE_METHOD
from .accounts_actions import qq_number
from .channel.formatting import GROUP_PREFIX
from shiori_sdk.accounts.targets import (
    ACCOUNT_SEND_METHOD,
    ACCOUNT_TARGETS_METHOD,
    account_send_media,
    AccountTarget,
)
from shiori_sdk.core.services import (
    ACCOUNTS,
    AVATARS,
    CHANNELS,
    HTTP,
    PROCESSES,
    RPC,
    TOOLS,
    WORKSPACE,
)

if TYPE_CHECKING:
    from shiori_sdk.channels.context import ChannelPluginContext


async def setup(ctx: "ChannelPluginContext") -> None:
    """Loads the plugin-owned accounts and contributes one multi-account channel."""
    from shiori_sdk.rpc import Concurrency

    from .accounts_runtime import QQAccountsRuntime
    from .accounts_store import QQAccountsStore
    from .read_attachment import ReadAttachmentTool

    ctx.require(TOOLS).register(
        ReadAttachmentTool(ctx.require(TOOLS)),
        risk="read-only",
        search_hint="QQ 附件 txt md 文件正文 引用文件 read_attachment",
        external_allowed=True,
    )

    runtime = QQAccountsRuntime(
        QQAccountsStore(ctx.require(WORKSPACE)),
        ctx.require(ACCOUNTS),
        ctx.require(AVATARS),
        processes=ctx.require(PROCESSES),
        http=ctx.require(HTTP),
    )
    await runtime.load()
    ctx.require(CHANNELS).add(runtime)

    def delete_account(config_ref: str) -> AccountDeletionPlan:
        return AccountDeletionPlan(
            disconnect=lambda: runtime.disconnect_account(config_ref),
            purge=lambda: runtime.purge_account(config_ref),
        )

    ctx.require(ACCOUNTS).on_delete(delete_account)
    ctx.require(ACCOUNTS).on_rules_change(runtime.save_rules)
    ctx.require(RPC).register(
        "accounts.settings",
        lambda payload: _settings(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.require(RPC).register("accounts.begin", runtime.begin_login)
    ctx.require(RPC).register(
        "accounts.start", lambda payload: _start(runtime, payload)
    )
    ctx.require(RPC).register(
        "accounts.disconnect", lambda payload: _disconnect(runtime, payload)
    )
    ctx.require(RPC).register(
        "accounts.stop",
        lambda payload: _stop(runtime, payload),
    )
    ctx.require(RPC).register(
        "accounts.cancel", lambda payload: _cancel(runtime, payload)
    )
    ctx.require(RPC).register(
        "accounts.logout", lambda payload: _logout(runtime, payload)
    )
    ctx.require(RPC).register(
        "accounts.managed_status",
        lambda payload: runtime.managed_status(str(payload["ref"])),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.require(RPC).register(
        "accounts.refresh_qrcode",
        lambda payload: runtime.refresh_qrcode(str(payload["ref"])),
    )
    ctx.require(RPC).register(
        "accounts.discover",
        lambda payload: _discover(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.require(RPC).register("accounts.send", lambda payload: _send(runtime, payload))
    ctx.require(RPC).register(
        ACCOUNT_TARGETS_METHOD,
        lambda payload: _discover(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.require(RPC).register(
        ACCOUNT_RESOLVE_METHOD,
        lambda payload: _resolve_account(runtime, payload),
        concurrency=Concurrency.READ_ONLY,
    )
    ctx.require(RPC).register(
        ACCOUNT_SEND_METHOD, lambda payload: _send_account(runtime, payload)
    )


async def _settings(runtime, payload: dict) -> dict:
    return runtime.settings(
        str(payload["account_id"]) if payload.get("account_id") else None
    )


async def _start(runtime, payload: dict) -> dict:
    return await runtime.start_login(
        str(payload["ref"]), str(payload.get("role_id") or "")
    )


async def _disconnect(runtime, payload: dict) -> dict:
    await runtime.disconnect(str(payload["account_id"]))
    return {"ok": True}


async def _stop(runtime, payload: dict) -> dict:
    await runtime.stop_login(str(payload["ref"]), str(payload.get("role_id") or ""))
    return {"ok": True}


async def _cancel(runtime, payload: dict) -> dict:
    await runtime.cancel_login(str(payload["ref"]), str(payload.get("role_id") or ""))
    return {"ok": True}


async def _logout(runtime, payload: dict) -> dict:
    await runtime.logout(str(payload["account_id"]))
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


async def _resolve_account(runtime, payload: dict) -> dict:
    """Resolve the actual NapCat inbound address with native target validation."""
    target = AccountTarget.from_arguments(payload)
    runtime.via_account(str(payload["account_id"]))
    if target.message_thread_id is not None:
        raise ValueError("QQ 不支持话题目标")
    number = qq_number(target.id, "目标")
    if target.kind == "group_member":
        qq_number(target.group_id, "群号")
    for mention in target.mention_ids:
        qq_number(mention, "提及成员")
    group = target.kind == "group"
    return AccountRoute(
        runtime.name,
        f"{GROUP_PREFIX}{number}" if group else number,
        "group" if group else "private",
    ).to_payload()


async def _send_account(runtime, payload: dict) -> dict:
    """Translate the shared account request into QQ's native target operation.

    Group mentions, group temporary sessions and images are QQ-native; the
    receipt carries the sending account's snapshot.
    """
    if payload.get("message_thread_id") is not None:
        raise ValueError("QQ 不支持话题目标")
    account_id = str(payload["account_id"])
    # Taken before sending so a completed send always returns its snapshot.
    via = runtime.via_account(account_id)
    result = await runtime.send_target(
        account_id,
        str(payload["target_kind"]),
        str(payload["target_id"]),
        str(payload["message"]),
        group_id=str(payload.get("group_id") or ""),
        mention_ids=tuple(payload.get("mention_ids") or ()),
        images=account_send_media(payload),
    )
    if payload["target_kind"] == "private":
        result["conversation"] = AccountRoute(
            runtime.name, result["chat_id"]
        ).to_payload()
    return {**result, VIA_ACCOUNT_KEY: via}
