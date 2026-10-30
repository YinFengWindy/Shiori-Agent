"""近期互动的渲染。用户本人的筛选留在宿主端口。"""

from __future__ import annotations

RECENT_MESSAGE_LIMIT = 12
"""近期互动最多保留的消息条数。宿主收集时使用同一上限。"""
RECENT_MESSAGE_CHAR_LIMIT = 6000
"""近期互动最多保留的总字数（至少保留最新一条）。"""


def render_recent_messages(recent_messages: list[dict[str, str]]) -> str:
    """把近期互动渲染成角色视角的对话文本（角色为「我」，用户为「你」）。"""
    if not recent_messages:
        return "（暂无近期互动）"
    return "\n".join(
        f"{'我' if item['role'] == 'assistant' else '你'}：{item['content']}"
        for item in recent_messages
    )
