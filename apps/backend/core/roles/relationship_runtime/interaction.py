"""角色与用户本人近期互动的收集与渲染，供关系快照与好感度初始化共用。"""

from __future__ import annotations

from typing import Any

from conversation.context_scope import UserContextThreads, belongs_to_user

from .models import _RECENT_MESSAGE_CHAR_LIMIT, _RECENT_MESSAGE_LIMIT


def collect_user_recent_messages(
    messages: list[dict[str, Any]],
    *,
    user_threads: UserContextThreads,
) -> list[dict[str, str]]:
    """返回按时间正序的近期互动：只取属于用户本人的消息（见 ``belongs_to_user``）。

    群友与陌生人的发言、角色在外部会话里的回复都不算角色与用户的互动；
    条数与总字数都有上限，超出时保留最新的部分。
    """
    pairs: list[dict[str, str]] = []
    total_chars = 0
    for message in reversed(messages):
        role = str(message.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        if not belongs_to_user(message, user_threads):
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        total_chars += len(content)
        if total_chars > _RECENT_MESSAGE_CHAR_LIMIT and pairs:
            break
        pairs.append({"role": role, "content": content})
        if len(pairs) >= _RECENT_MESSAGE_LIMIT:
            break
    pairs.reverse()
    return pairs


def render_recent_messages(recent_messages: list[dict[str, str]]) -> str:
    """把近期互动渲染成角色视角的对话文本（角色为「我」，用户为「你」）。"""
    if not recent_messages:
        return "（暂无近期互动）"
    return "\n".join(
        f"{'我' if item['role'] == 'assistant' else '你'}：{item['content']}"
        for item in recent_messages
    )
