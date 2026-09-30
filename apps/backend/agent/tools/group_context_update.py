"""Edit the current role's saved group notes and summaries without changing raw history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent.tools.base import Tool
from agent.tools.group_context import group_context_response
from conversation.service import ConversationService
from core.memory.external_writes import edit_group_environment
from core.memory.group_environment import GroupEnvironment


class UpdateGroupContextTool(Tool):
    """Edits a selected role-owned group through the shared memory write boundary."""

    name = "update_group_context"
    description = (
        "修改你记下的群笔记或群摘要。先用 lookup_group_context 找到群并读取当前内容，"
        "再用 group_thread_id 指定要改的群；可跨群、跨渠道修改当前角色所属的群。"
        "group_note 和 summary 至少给一个：提供的字段整篇替换，省略的字段保持原样，"
        "空字符串表示清空。返回修改后的笔记、摘要及摘要更新时间，不修改聊天或旁听原文。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "group_thread_id": {
                "type": "string",
                "description": "lookup_group_context 返回的目标群会话 ID。",
            },
            "group_note": {
                "type": "string",
                "description": "完整群笔记；省略则保留，空字符串清空。",
            },
            "summary": {
                "type": "string",
                "description": "完整群摘要；省略则保留，空字符串清空。",
            },
        },
        "required": ["group_thread_id"],
    }
    context_precedence = frozenset({"role_id"})

    def __init__(
        self, environment: GroupEnvironment, conversations: ConversationService
    ) -> None:
        self._environment = environment
        self._conversations = conversations

    async def execute(self, **kwargs: Any) -> str:
        """Validates the target and explicit edit fields before writing anything."""
        role_id = str(kwargs.get("role_id") or "")
        if not role_id:
            raise ValueError("当前回合没有角色，无法修改群笔记和摘要")
        thread_id = kwargs.get("group_thread_id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("必须提供 group_thread_id，请先查询群候选")
        changes = {
            key: kwargs[key] for key in ("group_note", "summary") if key in kwargs
        }
        if not changes or any(not isinstance(value, str) for value in changes.values()):
            raise ValueError(
                "group_note 或 summary 至少提供一个，且必须是字符串；空串表示清空"
            )
        thread = self._conversations.require_group_thread(role_id, thread_id.strip())
        contact = self._conversations.contacts_by_id(role_id).get(thread.contact_id)
        name = contact.display_name if contact else thread.external_thread_id
        snapshot = edit_group_environment(
            self._environment,
            role_id,
            thread.id,
            **changes,
            label=f"群「{name}」",
            updated_at=datetime.now().astimezone(),
        )
        return group_context_response(self._conversations, thread, snapshot)
