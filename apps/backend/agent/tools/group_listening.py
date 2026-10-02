"""角色开关群聊旁听的工具（#540）。

目标群用渠道 + 群的 chat_id 指定（即消息来源里的 channel 与 chat_id）。可用范围：

- 用户上下文（桌面、用户的私聊）：可以开关角色任意一个可旁听的群。
- 外部上下文：只有用户本人触发的回合拿得到这个工具（未声明外部可用，群友触发的
  回合由 #489 的白名单排除），并且只能开关当前这个群。

开关记录的操作方记为角色。
"""

from __future__ import annotations

import json
from typing import Any

from shiori_sdk.tools import Tool
from conversation.listening import GroupListeningControl, ListenableGroup
from conversation.service import network_thread_id


def _candidates(groups: list[ListenableGroup]) -> str:
    """可旁听的群，逐行「群名（channel=…, chat_id=…）：开/关」，写进报错给模型。"""
    if not groups:
        return "你目前没有可以旁听的群。"
    lines = [
        f"- {group.name}（channel={group.thread.channel}, "
        f"chat_id={group.thread.external_thread_id}）："
        f"{'旁听中' if group.enabled else '未旁听'}"
        for group in groups
    ]
    return "可以旁听的群：\n" + "\n".join(lines)


class SetGroupListeningTool(Tool):
    """Turns listening on or off for one of the role's groups, as the role.

    The turn's role, conversation, context and whether the user sent it come
    only from the execution context. ``channel`` and ``chat_id`` fall back to
    the turn's own conversation when the model omits them.
    """

    name = "set_group_listening"
    description = (
        "打开或关闭你对一个群的旁听。旁听时你会看到这个群里的所有消息（仍然只在被 @ "
        "或被回复时开口）。只在你的用户要求时使用。"
        "channel 和 chat_id 取自群消息来源里的 channel 与 chat_id；在群里时省略即指当前群，"
        "且在群里只能设置当前群。目标不是可旁听的群时，报错会列出可以旁听的群。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "群所在的渠道 ID；在群里时省略。",
            },
            "chat_id": {
                "type": "string",
                "description": "群的 chat_id（消息来源里的 chat_id）；在群里时省略。",
            },
            "enabled": {
                "type": "boolean",
                "description": "true 打开旁听，false 关闭旁听。",
            },
        },
        "required": ["enabled"],
    }
    context_precedence = frozenset(
        {"role_id", "thread_id", "context_scope", "sender_is_user"}
    )

    def __init__(self, listening: GroupListeningControl) -> None:
        self._listening = listening

    async def execute(self, **kwargs: Any) -> str:
        role_id = str(kwargs.get("role_id") or "")
        if not role_id:
            raise ValueError("当前回合没有角色，无法设置旁听")
        enabled = kwargs.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("enabled 必须是布尔值")
        target = network_thread_id(
            role_id, str(kwargs.get("channel") or ""), str(kwargs.get("chat_id") or "")
        )
        scope = kwargs.get("context_scope")
        # 失败即关：只有用户上下文，或用户本人在群里对当前群的操作才放行；
        # 上下文缺失或无法判定（非角色会话、后台回传）一律拒绝。
        if scope == "external" and kwargs.get("sender_is_user") == "true":
            if target != kwargs.get("thread_id"):
                raise PermissionError("在群里只能设置当前这个群的旁听")
        elif scope != "user":
            raise PermissionError("只有你的用户能让你设置旁听")
        try:
            settings = self._listening.set_enabled(
                role_id, target, enabled, operator="role"
            )
        except ValueError as error:
            candidates = _candidates(self._listening.groups(role_id))
            raise ValueError(f"这不是你可以旁听的群。{candidates}") from error
        return json.dumps(
            {
                "channel": kwargs.get("channel"),
                "chat_id": kwargs.get("chat_id"),
                "listening": settings.enabled,
            },
            ensure_ascii=False,
        )
