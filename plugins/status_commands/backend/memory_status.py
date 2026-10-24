"""Session-only memory status command and report."""

from __future__ import annotations

from typing import Any

from shiori_sdk.commands import CommandInput
from shiori_sdk.prompting import is_context_frame

from .formatting import content_to_text, preview_text


async def memory_status(command: CommandInput) -> str:
    """Reply with the session's consolidation status, leaving the session unchanged."""
    messages = [dict(message) for message in command.messages]
    last = min(max(0, command.last_consolidated), len(messages))
    return _format_memory_status_reply(messages, last)


def _format_memory_status_reply(
    messages: list[dict[str, Any]], last_consolidated: int
) -> str:
    consolidated_user = _count_real_user_messages(messages[:last_consolidated])
    total_user = _count_real_user_messages(messages)
    pending_user = max(0, total_user - consolidated_user)
    last_user_message = _latest_real_user_content(messages[:last_consolidated])

    lines = ["🧠 记忆整理状态："]
    if last_consolidated <= 0 or not last_user_message:
        lines.append("当前会话还没有完成过记忆整理。")
    elif pending_user == 0:
        lines.append("当前会话已经整理到最新的用户消息。")
    else:
        lines.append(f"上次整理到 {pending_user} 条用户消息之前。")
    if last_user_message:
        lines.extend(
            ["", "最后已整理的用户消息：", f"“{preview_text(last_user_message)}”"]
        )
    lines.extend(
        [
            "",
            f"尚未整理的用户消息数：{pending_user}",
            f"当前会话消息数：{len(messages)}",
        ]
    )
    return "\n".join(lines)


def _count_real_user_messages(messages: list[dict[str, Any]]) -> int:
    return sum(1 for item in messages if _is_real_user_message(item))


def _latest_real_user_content(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        if _is_real_user_message(item):
            return content_to_text(item.get("content", ""))
    return ""


def _is_real_user_message(item: dict[str, Any]) -> bool:
    if item.get("role") != "user":
        return False
    content = content_to_text(item.get("content", ""))
    return bool(content) and not is_context_frame(content)
