"""Authorize account operations and delegate target work to the owning plugin."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from agent.plugin_host.rpc import PluginRpcRegistry
from agent.account_delivery.turn_state import mark_account_delivery_sent
from core.accounts import AccountRegistry, AccountSnapshot
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.accounts.target_contract import (
    ACCOUNT_SEND_METHOD,
    ACCOUNT_TARGETS_METHOD,
    UncertainDeliveryError,
)


@dataclass(frozen=True)
class AccountSendReceipt:
    """Selected target and platform receipt for one explicit send attempt."""

    attempt_id: str
    account_id: str
    target_kind: str
    target_id: str
    platform_message_id: str
    ownership_current: bool


class AccountDelivery:
    """Checks live ownership and records each plugin send independently of turns."""

    def __init__(
        self,
        accounts: AccountRegistry,
        rpc: PluginRpcRegistry,
        ledger: AccountDeliveryLedger,
    ) -> None:
        self._accounts = accounts
        self._rpc = rpc
        self._ledger = ledger

    def _owned(self, account_id: str, role_id: str) -> AccountSnapshot:
        if not role_id:
            raise PermissionError("需要角色上下文")
        account = self._accounts.get(account_id)
        self._accounts.authorize(account_id, role_id)
        return account

    async def _call(self, plugin_id: str, method: str, payload: dict[str, Any]):
        resolved = self._rpc.resolve(f"plugin.{plugin_id}.{method}")
        if resolved is None or resolved[0] != plugin_id:
            raise RuntimeError(f"插件 {plugin_id} 未提供此能力")
        return await resolved[1](payload)

    def list_accounts(self, role_id: str) -> list[dict[str, object]]:
        """Report only this role's saved accounts and current plugin abilities."""
        if not role_id:
            raise PermissionError("需要角色上下文")
        rows: list[dict[str, object]] = []
        for account in self._accounts.list(role_id=role_id):
            row = account.record
            rows.append(
                {
                    "account_id": row.id,
                    "platform": row.platform,
                    "name": row.display_name,
                    "platform_account_id": row.platform_account_id,
                    "online": account.plugin_enabled
                    and account.runtime_active
                    and account.connection == "online",
                    "connection": account.connection,
                    "capabilities": sorted(account.capabilities),
                    "error": account.error,
                }
            )
        return rows

    async def targets(
        self, account_id: str, role_id: str, kind: str, group_id: str, member_id: str
    ) -> dict[str, Any]:
        """Return the plugin's actual directory coverage or lookup limitation."""
        account = self._owned(account_id, role_id)
        access = self._accounts.authorize(account_id, role_id)
        if not kind.strip():
            raise ValueError("查询类型不能为空")
        result = await self._call(
            account.record.plugin_id,
            ACCOUNT_TARGETS_METHOD,
            {
                "account_id": account_id,
                "kind": kind,
                "group_id": group_id,
                "member_id": member_id,
            },
        )
        if not self._accounts.validate_access(access):
            raise PermissionError("账号归属或连接状态已变化")
        if not isinstance(result, dict):
            raise RuntimeError("插件目标查询未返回有效结果")
        return result

    async def send(
        self,
        account_id: str,
        role_id: str,
        target_kind: str,
        target_id: str,
        message: str,
        message_thread_id: int | None,
        *,
        source: str = "passive_tool",
        media: list[str] | None = None,
    ) -> AccountSendReceipt:
        """Persist an attempt before sending, then record a real receipt or failure."""
        attempt = self._ledger.begin(
            role_id=role_id,
            account_id=account_id,
            target_kind=target_kind,
            target_id=target_id,
            target_options={"message_thread_id": message_thread_id},
            source=source,
        )
        try:
            account = self._owned(account_id, role_id)
            if not target_kind.strip() or not target_id.strip() or not message.strip():
                raise ValueError("目标类型、目标 ID 和消息不能为空")
            if media:
                raise ValueError("账号目标发送暂不支持媒体")
            access = self._accounts.authorize(account_id, role_id)
        except Exception as exc:
            self._ledger.mark_failed(attempt.attempt_id, type(exc).__name__)
            raise

        try:
            result = await self._call(
                account.record.plugin_id,
                ACCOUNT_SEND_METHOD,
                {
                    "account_id": account_id,
                    "target_kind": target_kind,
                    "target_id": target_id,
                    "message": message,
                    "message_thread_id": message_thread_id,
                },
            )
        except asyncio.CancelledError:
            mark_account_delivery_sent()
            self._ledger.mark_uncertain(attempt.attempt_id, "CancelledError")
            raise
        except (TimeoutError, ConnectionError, OSError, UncertainDeliveryError) as exc:
            # The platform may have accepted the payload before the link failed.
            mark_account_delivery_sent()
            self._ledger.mark_uncertain(attempt.attempt_id, type(exc).__name__)
            raise
        except Exception as exc:
            self._ledger.mark_failed(attempt.attempt_id, type(exc).__name__)
            raise
        message_id = (
            str(result.get("message_id") or "").strip()
            if isinstance(result, dict)
            else ""
        )
        if not message_id:
            mark_account_delivery_sent()
            self._ledger.mark_uncertain(attempt.attempt_id, "MissingReceipt")
            raise RuntimeError("平台未返回回执，发送结果不确定")
        mark_account_delivery_sent()
        self._ledger.mark_sent(attempt.attempt_id, message_id)
        return AccountSendReceipt(
            attempt_id=attempt.attempt_id,
            account_id=account_id,
            target_kind=target_kind,
            target_id=target_id,
            platform_message_id=message_id,
            ownership_current=self._accounts.validate_access(access),
        )
