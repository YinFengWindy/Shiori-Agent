"""Session-only memory status command and report."""

from __future__ import annotations

import logging
from typing import Any

from shiori_sdk.commands import CommandFrame, normalize_command
from shiori_sdk.lifecycle import LifecycleFrame
from shiori_sdk.prompting import is_context_frame

from .formatting import content_to_text, preview_text

logger = logging.getLogger("plugin.status_commands")
_SESSION_SLOT = "session:session"
_CTX_SLOT = "session:ctx"


class MemoryStatusCommandModule:
    """Reply with the current session consolidation status before retrieval."""

    slot = "status_commands.memory_status"
    requires = ("before_turn.acquire_session", _SESSION_SLOT)
    produces = (_CTX_SLOT,)

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        """Handle memory-status commands, preserving an earlier command abort."""
        if _CTX_SLOT in frame.slots or not isinstance(frame, CommandFrame):
            return frame
        state = frame.command
        command = normalize_command(state.content)
        if command not in {
            "/memorystatus",
            "/memory_status",
            "/compact_status",
        }:
            return frame
        if not state.has_session:
            return frame
        messages = [dict(message) for message in state.messages]
        last = max(0, state.last_consolidated)
        last = min(last, len(messages))
        logger.info(
            "[%s:%s] 命中命令: %s",
            "status_commands",
            self.__class__.__name__,
            command,
        )
        frame.abort_command(_format_memory_status_reply(messages, last))
        return frame


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
