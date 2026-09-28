"""Authorize account operations and delegate target work to the owning plugin."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from agent.plugin_host.rpc import PluginRpcRegistry
from agent.account_delivery.turn_state import mark_account_delivery_sent
from core.accounts import (
    VIA_ACCOUNT_KEY,
    AccountRegistry,
    AccountSnapshot,
    ViaAccount,
)
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.accounts.target_contract import (
    ACCOUNT_SEND_METHOD,
    ACCOUNT_TARGETS_METHOD,
    AccountTarget,
    UncertainDeliveryError,
)


@dataclass(frozen=True)
class AccountSendReceipt:
    """Selected target and platform receipt for one explicit send attempt.

    ``via_account`` is the sending plugin's ``ViaAccount`` snapshot, stored
    as-is with any message recorded for this send; None if it gave none.
    """

    attempt_id: str
    account_id: str
    channel: str
    target_kind: str
    target_id: str
    platform_message_id: str
    ownership_current: bool
    via_account: dict[str, str] | None = None


class AccountDelivery:
    """Checks live ownership and records each plugin send independently of turns.

    Callers name a channel (the channel plugin's ID); the role's account there
    is looked up in the registry, since a role holds at most one per plugin.
    """

    def __init__(
        self,
        accounts: AccountRegistry,
        rpc: PluginRpcRegistry,
        ledger: AccountDeliveryLedger,
    ) -> None:
        self._accounts = accounts
        self._rpc = rpc
        self._ledger = ledger

    def _channel_account(self, channel: str, role_id: str) -> AccountSnapshot:
        """The role's account on ``channel``; raises when it has none loaded."""
        if not role_id:
            raise PermissionError("需要角色上下文")
        channel = channel.strip()
        if not channel:
            raise ValueError("渠道不能为空")
        for account in self._accounts.list(role_id=role_id):
            if account.record.plugin_id == channel:
                return account
        raise LookupError(
            f"当前角色在渠道 {channel} 没有可用账号（未添加账号或渠道插件未加载）"
        )

    async def _call(self, plugin_id: str, method: str, payload: dict[str, Any]):
        resolved = self._rpc.resolve(f"plugin.{plugin_id}.{method}")
        if resolved is None or resolved[0] != plugin_id:
            raise RuntimeError(f"插件 {plugin_id} 未提供此能力")
        return await resolved[1](payload)

    def list_channels(self, role_id: str) -> list[dict[str, object]]:
        """This role's loaded channels and live abilities, without account IDs."""
        if not role_id:
            raise PermissionError("需要角色上下文")
        return [
            {
                "channel": account.record.plugin_id,
                "platform": account.record.platform,
                "name": account.record.display_name,
                "online": account.runtime_active and account.connection == "online",
                "connection": account.connection,
                "capabilities": sorted(account.capabilities),
                "error": account.error,
            }
            for account in self._accounts.list(role_id=role_id)
        ]

    async def targets(
        self, channel: str, role_id: str, kind: str, group_id: str, member_id: str
    ) -> dict[str, Any]:
        """Return the plugin's actual directory coverage or lookup limitation."""
        account = self._channel_account(channel, role_id)
        account_id = account.record.id
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
        channel: str,
        role_id: str,
        target: AccountTarget,
        message: str,
        *,
        source: str = "passive_tool",
        media: list[str] | None = None,
    ) -> AccountSendReceipt:
        """Persist an attempt before sending, then record a real receipt or failure.

        Resolving the channel happens first: a role without an account there
        has nothing to attempt, so nothing is recorded.
        """
        account = self._channel_account(channel, role_id)
        account_id = account.record.id
        attempt = self._ledger.begin(
            role_id=role_id,
            account_id=account_id,
            target_kind=target.kind,
            target_id=target.id,
            target_options={
                "message_thread_id": target.message_thread_id,
                "group_id": target.group_id,
                "mention_ids": list(target.mention_ids),
            },
            source=source,
        )
        try:
            if not message.strip():
                raise ValueError("消息不能为空")
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
                {"account_id": account_id, "message": message, **target.to_payload()},
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
        via = result.get(VIA_ACCOUNT_KEY) if isinstance(result, dict) else None
        return AccountSendReceipt(
            attempt_id=attempt.attempt_id,
            account_id=account_id,
            channel=account.record.plugin_id,
            target_kind=target.kind,
            target_id=target.id,
            platform_message_id=message_id,
            ownership_current=self._accounts.validate_access(access),
            # Checked only after the receipt is recorded: the platform already
            # accepted the message, so a malformed snapshot must not hide that.
            via_account=(
                None
                if via is None
                else ViaAccount.for_account(via, account.record).to_metadata()
            ),
        )
