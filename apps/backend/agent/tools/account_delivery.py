"""Model-facing adapters for channel discovery and explicit message delivery.

The model picks a channel (a channel plugin's ID); account IDs never appear in
arguments or results, because the role holds at most one account per channel.
"""

from __future__ import annotations

import json
from typing import Any

from agent.account_delivery import AccountDelivery
from agent.tools.base import Tool
from agent.tools.message_push import record_delivered_push
from bus.event_bus import EventBus
from bus.events_lifecycle import ExternalTextPushed
from core.accounts.target_contract import (
    ACCOUNT_TARGET_PROPERTIES,
    USER_TARGET,
    AccountTarget,
    account_send_media,
    is_user_target,
)
from core.common.channel_chat_types import CHAT_TYPE_PRIVATE


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
    """Sends text and/or images through the role's account on one channel.

    The ``user`` target reaches the desktop user's private chat on the channel,
    resolved from their bindings (``AccountDelivery.user_chat``); such a send
    is also recorded in the role session under that chat's thread, like a
    ``message_push`` delivery, so the chat shows it.
    """

    name = "account_send"
    description = (
        "通过当前角色在指定渠道的账号向一个明确目标发送文本和/或图片，返回平台真实消息回执。"
        f"发给你的用户时用 target_kind={USER_TARGET}，只需指定 channel，"
        "由系统按用户的身份绑定找到其私聊；用户在该渠道未绑定或还没私聊过你的账号时会报错。"
        "其他目标先调用 account_targets 获取目标 ID；不接受模糊名称。"
        "target_kind、message_thread_id、group_id 和 mention_ids 的有效性由渠道插件校验。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "渠道 ID，取自 account_list 的 channel。",
            },
            # The shared target fields plus the ``user`` kind. That kind is
            # model-only: this tool resolves it from the user's bindings before
            # sending, so it stays out of the shared schema (message_push
            # retargeting and plugins never resolve it).
            **ACCOUNT_TARGET_PROPERTIES,
            "target_kind": {
                "type": "string",
                "description": ACCOUNT_TARGET_PROPERTIES["target_kind"]["description"]
                + f"另可用 {USER_TARGET}：你的用户，按身份绑定发到其私聊，无需 target_id。",
            },
            "target_id": {
                "type": "string",
                "description": ACCOUNT_TARGET_PROPERTIES["target_id"]["description"]
                + f"{USER_TARGET} 目标不填。",
            },
            "message": {
                "type": "string",
                "description": "要发送的文本；只发图片时可省略。",
            },
            "media": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选，要随消息发送的图片本地路径或 URL 列表。",
            },
        },
        "required": ["channel", "target_kind"],
    }
    # The turn's session and whether its pushes commit with it come from the
    # execution context, never from model arguments.
    context_precedence = frozenset(
        {"role_id", "session_key", "defer_push_session_sync"}
    )

    def __init__(self, delivery: AccountDelivery, event_bus: EventBus) -> None:
        self._delivery = delivery
        self._event_bus = event_bus

    @property
    def delivery(self) -> AccountDelivery:
        """Provides the owning service to host delivery orchestration."""
        return self._delivery

    async def execute(self, **kwargs: Any) -> str:
        channel = str(kwargs["channel"])
        role_id = str(kwargs.get("role_id") or "")
        message = str(kwargs.get("message") or "")
        media = list(account_send_media(kwargs))
        user_chat = (
            self._delivery.user_chat(channel, role_id)
            if is_user_target(kwargs)
            else None
        )
        target = (
            user_chat.target
            if user_chat is not None
            else AccountTarget.from_arguments(kwargs)
        )
        receipt = await self._delivery.send(
            channel, role_id, target, message, media=media
        )
        if user_chat is not None:
            # Recorded like a pushed message: with the turn that sent it, or
            # at once outside a live turn.
            await record_delivered_push(
                self._event_bus,
                ExternalTextPushed(
                    session_key=str(kwargs.get("session_key") or ""),
                    role_id=role_id,
                    channel=user_chat.chat.channel,
                    chat_id=user_chat.chat.chat_id,
                    text=message,
                    in_turn=str(kwargs.get("defer_push_session_sync") or "") == "true",
                    external_message_id=receipt.platform_message_id,
                    tool=self.name,
                    media=tuple(media),
                    message_metadata={
                        "chat_type": CHAT_TYPE_PRIVATE,
                        **receipt.message_metadata(),
                    },
                ),
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
