"""按需查询当前角色的群笔记与摘要；跨群、跨渠道，不返回聊天原文（#560）。"""

from __future__ import annotations

import json
from typing import Any

from agent.tools.base import Tool
from conversation.models import ThreadRecord
from conversation.service import ConversationService
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentSnapshot

_PAGE_SIZE = 20


def group_context_response(
    conversations: ConversationService,
    thread: ThreadRecord,
    snapshot: GroupEnvironmentSnapshot,
) -> str:
    """Serializes the same current group identity and saved fields for both tools."""
    contact = conversations.contacts_by_id(thread.role_id).get(thread.contact_id)
    return json.dumps(
        {
            "group_thread_id": thread.id,
            "channel": thread.channel,
            "name": contact.display_name if contact else thread.external_thread_id,
            "group_note": snapshot.group_note,
            "summary": snapshot.recent_activity,
            "summary_updated_at": snapshot.summary_updated_at,
        },
        ensure_ascii=False,
    )


class LookupGroupContextTool(Tool):
    """Finds the current role's groups and reads their saved notes and summaries."""

    name = "lookup_group_context"
    description = (
        "查你记下的群笔记和最新群摘要，可跨群、跨渠道查询当前角色所属的群。"
        "先用 name 按群名查候选（不区分大小写），再用 group_thread_id 读指定群；"
        "不传 name 或 group_thread_id 时分页列出所有群，page 从 1 开始。"
        "只返回群笔记、摘要及摘要更新时间，没有的字段为空字符串；"
        "可查较早的记录，不返回聊天或旁听原文，不查询私聊。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "群名的一部分；与 group_thread_id 不能同时使用。",
            },
            "group_thread_id": {
                "type": "string",
                "description": "从候选列表选中的群会话 ID，用于读取该群笔记和摘要。",
            },
            "page": {
                "type": "integer",
                "minimum": 1,
                "description": "列候选时的页码，默认 1；有下一页时返回 next_page。",
            },
        },
    }
    context_precedence = frozenset({"role_id"})

    def __init__(
        self, environment: GroupEnvironment, conversations: ConversationService
    ) -> None:
        self._environment = environment
        self._conversations = conversations

    async def execute(self, **kwargs: Any) -> str:
        """Lists group candidates or reads the explicitly selected role-owned group."""
        role_id = str(kwargs.get("role_id") or "")
        if not role_id:
            raise ValueError("当前回合没有角色，无法查群笔记和摘要")
        name = str(kwargs.get("name") or "").strip()
        group_thread_id = str(kwargs.get("group_thread_id") or "").strip()
        page = kwargs.get("page", 1)
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page 必须是从 1 开始的整数")
        if group_thread_id and (name or page != 1):
            raise ValueError("按 group_thread_id 读取时不能同时按群名查找或翻页")

        if group_thread_id:
            # 先按角色归属及群类型校验，再访问群环境层，避免读取私聊或旧绑定。
            thread = self._conversations.require_group_thread(role_id, group_thread_id)
            snapshot = self._environment.read(role_id, group_thread_id)
            return group_context_response(self._conversations, thread, snapshot)

        groups = self._groups(role_id)
        matched = [
            group for group in groups if name.casefold() in group["name"].casefold()
        ]
        start = (page - 1) * _PAGE_SIZE
        return json.dumps(
            {
                "total": len(matched),
                "page": page,
                "next_page": page + 1 if start + _PAGE_SIZE < len(matched) else None,
                "candidates": matched[start : start + _PAGE_SIZE],
            },
            ensure_ascii=False,
        )

    def _groups(self, role_id: str) -> list[dict[str, str]]:
        contacts = self._conversations.contacts_by_id(role_id)
        return [
            {
                "group_thread_id": thread.id,
                "channel": thread.channel,
                "name": (
                    contact.display_name
                    if (contact := contacts.get(thread.contact_id)) is not None
                    else thread.external_thread_id
                ),
            }
            for thread in sorted(
                self._conversations.list_group_threads(role_id),
                key=lambda item: item.id,
            )
        ]
