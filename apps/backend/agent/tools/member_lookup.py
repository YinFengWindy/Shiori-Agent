"""查成员档案的工具（#540）。

成员档案按「渠道 + 成员 ID」保存（#498）。按 ID 查返回档案；按名字查时匹配档案
记录过的全部昵称（含旧昵称），只返回带 ID 与渠道的候选，由模型再按 ID 查档案。

渠道规则：外部上下文（群聊、陌生私聊）固定查当前会话所在的渠道。其他回合由
``member_channel`` 指定；按名字查时可省略，表示在所有渠道里找，按 ID 查时必填。
渠道参数不叫 ``channel``，免得省略时被执行上下文里当前对话的渠道（桌面等）顶替。
声明外部上下文可用，群友触发的回合也能用。
"""

from __future__ import annotations

import json
from typing import Any

from shiori_sdk.tools import Tool
from conversation.service import ConversationService
from core.memory.member_profiles import MemberKey, MemberProfile, MemberProfiles

# 按名字查时最多返回的候选数。
_MAX_CANDIDATES = 10


def _matches_name(profile: MemberProfile, name: str) -> bool:
    """档案记录过的任一昵称（含旧昵称）是否包含 ``name``，不区分大小写。"""
    needle = name.casefold()
    return any(needle in nickname.casefold() for nickname in profile.nicknames)


class LookupMemberTool(Tool):
    """Looks up the role's member profiles, by member ID or by name.

    The turn's role, conversation and context come only from the execution
    context. In the external context the lookup stays on the turn's channel.
    """

    name = "lookup_member"
    description = (
        "查你记下的成员档案（群友、陌生人）。按 member_id 查返回这个人的档案；"
        "只知道名字时用 name 查，会匹配他用过的所有昵称（含旧昵称），返回带 member_id "
        "与渠道的候选，再用 member_id 查档案。member_id 即消息来源里的 sender_id。"
        "在群聊或陌生私聊里只查当前渠道；其他时候按名字查可省略 member_channel 查所有渠道，"
        "按 member_id 查必须给出 member_channel。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "member_id": {
                "type": "string",
                "description": "成员 ID（消息来源里的 sender_id）。与 name 二选一。",
            },
            "name": {
                "type": "string",
                "description": "成员的名字或昵称的一部分。与 member_id 二选一。",
            },
            "member_channel": {
                "type": "string",
                "description": "成员所在的渠道 ID（消息来源里的 channel）；在群聊或陌生私聊里固定为当前渠道。",
            },
        },
    }
    context_precedence = frozenset({"role_id", "thread_id", "context_scope"})

    def __init__(
        self, members: MemberProfiles, conversations: ConversationService
    ) -> None:
        self._members = members
        self._conversations = conversations

    async def execute(self, **kwargs: Any) -> str:
        role_id = str(kwargs.get("role_id") or "")
        if not role_id:
            raise ValueError("当前回合没有角色，无法查成员档案")
        member_id = str(kwargs.get("member_id") or "").strip()
        name = str(kwargs.get("name") or "").strip()
        if bool(member_id) == bool(name):
            raise ValueError("member_id 与 name 必须且只能给一个")
        channel = self._channel(kwargs)
        if member_id:
            if not channel:
                raise ValueError("按 member_id 查需要给出 member_channel")
            return self._by_id(role_id, MemberKey(channel, member_id))
        return self._by_name(role_id, channel, name)

    def _channel(self, kwargs: dict[str, Any]) -> str:
        """本次查询的渠道：外部上下文固定为当前会话的渠道；其他回合取参数，可为空。"""
        channel = str(kwargs.get("member_channel") or "").strip()
        if kwargs.get("context_scope") != "external":
            return channel
        thread_id = str(kwargs.get("thread_id") or "")
        thread = self._conversations.get_thread(thread_id)
        if thread is None:
            raise ValueError(f"找不到当前会话: {thread_id}")
        if channel and channel != thread.channel:
            raise ValueError("在这里只能查当前渠道的成员")
        return thread.channel

    def _by_id(self, role_id: str, key: MemberKey) -> str:
        profile = self._members.read(role_id, key)
        if profile is None:
            return f"没有 {key.channel} 渠道成员 {key.sender_id} 的档案"
        return json.dumps(
            {
                "member_id": key.sender_id,
                "channel": key.channel,
                "name": profile.call_name,
                "nicknames": list(profile.nicknames),
                "brief": profile.brief,
                "profile": profile.profile,
            },
            ensure_ascii=False,
        )

    def _by_name(self, role_id: str, channel: str, name: str) -> str:
        """``channel`` 为空时在所有渠道里找。"""
        matched = [
            profile
            for profile in self._members.list(role_id)
            if (not channel or profile.key.channel == channel)
            and _matches_name(profile, name)
        ]
        return json.dumps(
            {
                "total": len(matched),
                "candidates": [
                    {
                        "member_id": profile.key.sender_id,
                        "channel": profile.key.channel,
                        "name": profile.call_name,
                        "nicknames": list(profile.nicknames),
                    }
                    for profile in matched[:_MAX_CANDIDATES]
                ],
            },
            ensure_ascii=False,
        )
