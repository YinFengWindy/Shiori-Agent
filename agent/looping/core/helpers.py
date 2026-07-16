"""Agent loop 共享类型、策略与纯辅助函数。"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeAlias, cast

from bus.events import CodingAgentCompletionItem, InboundItem, InboundMessage

from ..interrupt import TurnInterruptState

logger = logging.getLogger("agent.loop")
_MANUAL_CONSOLIDATION_TIMEOUT_SECONDS = 30.0

StreamDelta: TypeAlias = dict[str, str] | str
StreamSink: TypeAlias = Callable[[StreamDelta], Awaitable[None]]
StreamSinkFactory: TypeAlias = Callable[[object], StreamSink | None]
StreamSupportPolicy: TypeAlias = Callable[[str], bool]


def _is_positive_int(value: str) -> bool:
    try:
        return int(value) > 0
    except ValueError:
        return False


_STREAM_SUPPORT_POLICIES: dict[str, StreamSupportPolicy] = {
    "telegram": _is_positive_int,
}


def _supports_stream_events(channel: str, chat_id: str) -> bool:
    policy = _STREAM_SUPPORT_POLICIES.get(channel)
    return bool(policy is not None and policy(chat_id))


def _suppresses_stream_events(msg: object) -> bool:
    metadata: object = getattr(msg, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    typed = cast(dict[str, object], metadata)
    return bool(typed.get("suppress_stream_events"))


def _item_content(item: InboundItem) -> str:
    if isinstance(item, InboundMessage):
        return item.content
    if isinstance(item, CodingAgentCompletionItem):
        return f"[Coding Agent 运行更新] {item.event.label or item.event.status}"
    return (
        f"[后台任务完成] {item.event.label or item.event.status or item.event.job_id}"
    )



def _build_resume_content(state: TurnInterruptState, new_message: str) -> str:
    """将中断态 + 用户补充消息拼装为续跑输入。"""
    parts = [
        "【上一轮任务（被用户中断）】",
        state.original_user_message,
        "",
        "【上一轮已生成但未完成的中间结果】",
        state.partial_reply or "（无）",
    ]
    if state.tools_used:
        parts.append(f"已使用工具：{', '.join(state.tools_used)}")
    parts += [
        "",
        "【用户补充要求】",
        new_message,
    ]
    return "\n".join(parts)
