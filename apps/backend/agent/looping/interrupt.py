"""
被动 AgentLoop 中断机制 — 数据结构与协议。

Channel 层识别 /stop 命令后，通过 InterruptController.request_interrupt()
走控制面打断当前正在执行的 turn，不经过 MessageBus 数据面。
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol

_DEFAULT_TTL_S = 1800  # 30 分钟

# 插件提交的外部回合（#721）与同一角色的桌面/渠道回合共用角色会话的 session_key，
# 但不登记为该会话的可中断回合。它的任务内此值为 True：进度回写与中断续跑都据此
# 跳过，既不写进排队中的桌面/渠道回合状态，也不消费它们留下的中断态。
_DETACHED_TURN: ContextVar[bool] = ContextVar("detached_turn", default=False)


def mark_detached_turn() -> None:
    """Detaches the current task's turn from session interrupt tracking.

    Call it only at the start of the turn's own task, so the flag never
    reaches any other turn.
    """
    _DETACHED_TURN.set(True)


def in_detached_turn() -> bool:
    """Whether the current task runs a turn detached from interrupt tracking."""
    return _DETACHED_TURN.get()


@dataclass
class TurnInterruptState:
    """一个被中断的 turn 的快照，供控制面和持久化边界共同使用。"""

    session_key: str
    original_user_message: str
    original_metadata: dict = field(default_factory=dict)
    partial_reply: str = ""
    partial_thinking: str | None = None
    tools_used: list[str] = field(default_factory=list)
    tool_chain_partial: list[dict] = field(default_factory=list)
    interrupted_by: str = "/stop"
    interrupted_at: float = field(default_factory=time.monotonic)
    ttl_seconds: int = _DEFAULT_TTL_S

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.interrupted_at) > self.ttl_seconds


def tracked_turn_state(
    states: Mapping[str, "TurnInterruptState"], session_key: str
) -> "TurnInterruptState | None":
    """The state the current turn reports its progress into, if it is tracked.

    A detached turn has none, even when another turn of the same session is
    tracked under ``session_key``.
    """
    if in_detached_turn():
        return None
    return states.get(session_key)


@dataclass
class InterruptResult:
    """request_interrupt() 的返回值。"""

    status: str  # "interrupted" | "idle"
    session_key: str = ""
    message: str = ""
    state: TurnInterruptState | None = None


class InterruptController(Protocol):
    """Channel 层调用的中断协议，由 AgentLoop 实现。"""

    def request_interrupt(
        self,
        session_key: str,
        sender: str = "",
        command: str = "/stop",
    ) -> InterruptResult: ...
