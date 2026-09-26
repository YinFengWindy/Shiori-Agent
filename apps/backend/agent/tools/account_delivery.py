"""Role-scoped communication account discovery and explicit text delivery."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from collections.abc import Iterator

from agent.plugin_host.rpc import PluginRpcRegistry
from agent.tools.base import Tool
from core.accounts import AccountRegistry, AccountSnapshot
from core.accounts.target_contract import ACCOUNT_SEND_METHOD, ACCOUNT_TARGETS_METHOD

_delivery_state: ContextVar[dict[str, bool] | None] = ContextVar(
    "account_delivery_state", default=None
)


@contextmanager
def account_delivery_scope(state: dict[str, bool]) -> Iterator[None]:
    """Track successful account sends within one model attempt only."""
    token = _delivery_state.set(state)
    try:
        yield
    finally:
        _delivery_state.reset(token)


class AccountDelivery:
    """Checks live ownership and delegates platform operations to active plugins."""

    def __init__(self, accounts: AccountRegistry, rpc: PluginRpcRegistry) -> None:
        self._accounts = accounts
        self._rpc = rpc

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

    def list_accounts(self, role_id: str) -> str:
        """Report only this role's saved accounts and current plugin capabilities."""
        if not role_id:
            raise PermissionError("需要角色上下文")
        rows = []
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
        return json.dumps(rows, ensure_ascii=False)

    async def targets(
        self, account_id: str, role_id: str, kind: str, group_id: str, member_id: str
    ) -> str:
        """Expose each plugin's actual directory coverage or lookup limitation."""
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
        return json.dumps(result, ensure_ascii=False)

    async def send(
        self,
        account_id: str,
        role_id: str,
        target_kind: str,
        target_id: str,
        message: str,
        message_thread_id: int | None,
    ) -> str:
        """Send once to an explicit target and return the platform receipt."""
        account = self._owned(account_id, role_id)
        if not target_kind.strip() or not target_id.strip() or not message.strip():
            raise ValueError("目标类型、目标 ID 和消息不能为空")
        access = self._accounts.authorize(account_id, role_id)
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
        if (
            not isinstance(result, dict)
            or not str(result.get("message_id") or "").strip()
        ):
            raise RuntimeError("平台未返回消息回执")
        return json.dumps(
            {
                "status": "sent",
                "account_id": account_id,
                "target_kind": target_kind,
                "target_id": target_id,
                "platform_message_id": str(result["message_id"]),
                "ownership_current": self._accounts.validate_access(access),
            },
            ensure_ascii=False,
        )


class AccountListTool(Tool):
    """Lists authorized communication identities and their live abilities."""

    name = "account_list"
    description = "查询当前角色可用的通讯账号、实时连接状态和目标能力。"
    parameters = {"type": "object", "properties": {}}
    context_precedence = frozenset({"role_id"})

    def __init__(self, delivery: AccountDelivery) -> None:
        self._delivery = delivery

    async def execute(self, **kwargs: Any) -> str:
        return self._delivery.list_accounts(str(kwargs.get("role_id") or ""))


class AccountTargetsTool(Tool):
    """Queries one account's supported target directory or specific member."""

    name = "account_targets"
    description = "查询指定账号插件实际支持的目标。kind 可为 friends、groups、members、known 或 member；成员查询需 group_id，指定成员还需 member_id。不支持的查询由插件明确说明。"
    parameters = {
        "type": "object",
        "properties": {
            "account_id": {"type": "string"},
            "kind": {"type": "string"},
            "group_id": {"type": "string"},
            "member_id": {"type": "string"},
        },
        "required": ["account_id", "kind"],
    }
    context_precedence = frozenset({"role_id"})

    def __init__(self, delivery: AccountDelivery) -> None:
        self._delivery = delivery

    async def execute(self, **kwargs: Any) -> str:
        return await self._delivery.targets(
            str(kwargs["account_id"]),
            str(kwargs.get("role_id") or ""),
            str(kwargs["kind"]),
            str(kwargs.get("group_id") or ""),
            str(kwargs.get("member_id") or ""),
        )


class AccountSendTool(Tool):
    """Sends a text message with an explicit account and target selection."""

    name = "account_send"
    description = "使用指定账号向一个明确目标发送文本，返回平台真实消息回执。先调用 account_targets 获取目标 ID；不接受模糊名称。target_kind 和可选 message_thread_id 的有效值由账号插件校验。"
    parameters = {
        "type": "object",
        "properties": {
            "account_id": {"type": "string"},
            "target_kind": {"type": "string"},
            "target_id": {"type": "string"},
            "message": {"type": "string"},
            "message_thread_id": {"type": "integer"},
        },
        "required": ["account_id", "target_kind", "target_id", "message"],
    }
    context_precedence = frozenset({"role_id"})

    def __init__(self, delivery: AccountDelivery) -> None:
        self._delivery = delivery

    async def execute(self, **kwargs: Any) -> str:
        receipt = await self._delivery.send(
            str(kwargs["account_id"]),
            str(kwargs.get("role_id") or ""),
            str(kwargs["target_kind"]),
            str(kwargs["target_id"]),
            str(kwargs["message"]),
            kwargs.get("message_thread_id"),
        )
        state = _delivery_state.get()
        if state is not None:
            state["sent"] = True
        return receipt
