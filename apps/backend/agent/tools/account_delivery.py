"""Model-facing adapters for account discovery and explicit text delivery."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from agent.account_delivery import AccountDelivery
from agent.tools.base import Tool


class AccountListTool(Tool):
    """Lists authorized communication identities and their live abilities."""

    name = "account_list"
    description = "查询当前角色可用的通讯账号、实时连接状态和目标能力。"
    parameters = {"type": "object", "properties": {}}
    context_precedence = frozenset({"role_id"})

    def __init__(self, delivery: AccountDelivery) -> None:
        self._delivery = delivery

    async def execute(self, **kwargs: Any) -> str:
        return json.dumps(
            self._delivery.list_accounts(str(kwargs.get("role_id") or "")),
            ensure_ascii=False,
        )


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
        result = await self._delivery.targets(
            str(kwargs["account_id"]),
            str(kwargs.get("role_id") or ""),
            str(kwargs["kind"]),
            str(kwargs.get("group_id") or ""),
            str(kwargs.get("member_id") or ""),
        )
        return json.dumps(result, ensure_ascii=False)


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

    @property
    def delivery(self) -> AccountDelivery:
        """Provides the owning service to host delivery orchestration."""
        return self._delivery

    async def execute(self, **kwargs: Any) -> str:
        receipt = await self._delivery.send(
            str(kwargs["account_id"]),
            str(kwargs.get("role_id") or ""),
            str(kwargs["target_kind"]),
            str(kwargs["target_id"]),
            str(kwargs["message"]),
            kwargs.get("message_thread_id"),
        )
        return json.dumps(asdict(receipt), ensure_ascii=False)
