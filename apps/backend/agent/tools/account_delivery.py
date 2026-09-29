"""Model-facing adapters for channel discovery and explicit text delivery.

The model picks a channel (a channel plugin's ID); account IDs never appear in
arguments or results, because the role holds at most one account per channel.
"""

from __future__ import annotations

import json
from typing import Any

from agent.account_delivery import AccountDelivery
from agent.tools.base import Tool
from core.accounts.target_contract import ACCOUNT_TARGET_PROPERTIES, AccountTarget


class AccountListTool(Tool):
    """Lists the role's channels and their live abilities."""

    name = "account_list"
    description = "查询当前角色可用的通讯渠道（channel）、实时连接状态和目标能力。"
    parameters = {"type": "object", "properties": {}}
    context_precedence = frozenset({"role_id"})

    def __init__(self, delivery: AccountDelivery) -> None:
        self._delivery = delivery

    async def execute(self, **kwargs: Any) -> str:
        return json.dumps(
            self._delivery.list_channels(str(kwargs.get("role_id") or "")),
            ensure_ascii=False,
        )


class AccountTargetsTool(Tool):
    """Queries one channel's supported target directory or specific member."""

    name = "account_targets"
    description = "查询当前角色在指定渠道实际支持的目标。kind 可为 friends、groups、members、known 或 member；成员查询需 group_id，指定成员还需 member_id。不支持的查询由渠道插件明确说明。"
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "渠道 ID，取自 account_list 的 channel。",
            },
            "kind": {"type": "string"},
            "group_id": {"type": "string"},
            "member_id": {"type": "string"},
        },
        "required": ["channel", "kind"],
    }
    context_precedence = frozenset({"role_id"})

    def __init__(self, delivery: AccountDelivery) -> None:
        self._delivery = delivery

    async def execute(self, **kwargs: Any) -> str:
        result = await self._delivery.targets(
            str(kwargs["channel"]),
            str(kwargs.get("role_id") or ""),
            str(kwargs["kind"]),
            str(kwargs.get("group_id") or ""),
            str(kwargs.get("member_id") or ""),
        )
        return json.dumps(result, ensure_ascii=False)


def shared_account_delivery(tools: Any) -> AccountDelivery | None:
    """The delivery service behind a tool registry's ``account_send``, if any.

    Host delivery paths outside a passive turn (proactive retargeting) reach
    the role's channel accounts through the same service the model's tool uses.
    """
    tool = tools.get_tool(AccountSendTool.name) if tools is not None else None
    return tool.delivery if isinstance(tool, AccountSendTool) else None


class AccountSendTool(Tool):
    """Sends a text message through the role's account on one channel."""

    name = "account_send"
    description = "通过当前角色在指定渠道的账号向一个明确目标发送文本，返回平台真实消息回执。先调用 account_targets 获取目标 ID；不接受模糊名称。target_kind、message_thread_id、group_id 和 mention_ids 的有效性由渠道插件校验。"
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "渠道 ID，取自 account_list 的 channel。",
            },
            **ACCOUNT_TARGET_PROPERTIES,
            "message": {"type": "string"},
        },
        "required": ["channel", "target_kind", "target_id", "message"],
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
            str(kwargs["channel"]),
            str(kwargs.get("role_id") or ""),
            AccountTarget.from_arguments(kwargs),
            str(kwargs["message"]),
        )
        return json.dumps(
            {
                "attempt_id": receipt.attempt_id,
                "channel": receipt.channel,
                "target_kind": receipt.target_kind,
                "target_id": receipt.target_id,
                "platform_message_id": receipt.platform_message_id,
                "ownership_current": receipt.ownership_current,
            },
            ensure_ascii=False,
        )
