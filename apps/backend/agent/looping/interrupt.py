"""
被动 AgentLoop 中断机制 — 数据结构与协议。

Channel 层识别 /stop 命令后，通过 InterruptController.request_interrupt()
走控制面打断当前正在执行的 turn，不经过 MessageBus 数据面。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol

from shiori_sdk.channels.chat_types import is_group_chat_type

_DEFAULT_TTL_S = 1800  # 30 分钟

# 插件提交的外部回合（#721）与同一角色的桌面/渠道回合共用角色会话的 session_key，
# 但不登记为该会话的可中断回合。外部回合的任务及其派生任务（观察者 fanout、工具、
# 记忆整理等）里此值为 True：进度回写与中断续跑都据此跳过，既不写进排队中的桌面/
# 渠道回合状态，也不消费它们留下的中断态。每个回合任务开头由 ``run_turn_task`` 显式
# 设定，所以从外部回合里派生出的新回合仍按自己的登记处理，不会继承此值。
_DETACHED_TURN: ContextVar[bool] = ContextVar("detached_turn", default=False)
_TRACKING_KEY: ContextVar[str] = ContextVar("turn_tracking_key", default="")


def turn_tracking_key(
    session_key: str,
    channel: str = "",
    chat_id: str = "",
    *,
    account_id: str = "",
    chat_type: str = "",
    message_thread_id: str = "",
) -> str:
    """Identify a complete transport origin, rejecting partial external addresses.

    Only an unspecified origin or the exact desktop address uses the bare
    session key. Legacy external addresses may omit all extended fields.
    """
    if not any((channel, chat_id, account_id, chat_type, message_thread_id)):
        return session_key
    if (
        channel == "desktop"
        and chat_id == session_key
        and not account_id
        and not message_thread_id
        and chat_type in ("", "private")
    ):
        return session_key
    if (
        not channel
        or not chat_id
        or channel == "desktop"
        or ((account_id or message_thread_id) and not chat_type)
    ):
        raise ValueError("External turn origin requires channel, chat and chat type")
    base = f"{session_key}\x1f{channel}\x1f{chat_id}"
    if account_id or chat_type or message_thread_id:
        return "\x1f".join(
            (
                base,
                account_id,
                "group" if is_group_chat_type(chat_type) else chat_type,
                chat_id,
                message_thread_id,
            )
        )
    return base


def current_tracking_key(session_key: str) -> str:
    """Resolve progress/resume writes to the current task's registered chat."""
    return _TRACKING_KEY.get() or session_key


async def run_turn_task[T](
    operation: Callable[[], Awaitable[T]], *, detached: bool, tracking_key: str = ""
) -> T:
    """Runs ``operation()`` as the body of one turn's own task.

    Hand it to ``asyncio.create_task``: the task's copied context records
    whether this turn is ``detached`` from session interrupt tracking,
    whatever the creating task was. Tasks the turn creates inherit it as part
    of the same turn. The coroutine is created only once the task runs, so a
    task cancelled before its first step leaves none behind.
    """
    _DETACHED_TURN.set(detached)
    _TRACKING_KEY.set(tracking_key)
    if detached:
        from agent.turns.reply_interruption import reply_interruption_scope

        with reply_interruption_scope(None):
            return await operation()
    return await operation()


def in_detached_turn() -> bool:
    """Whether the current task works for a turn detached from interrupt tracking."""
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
    return states.get(current_tracking_key(session_key))


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
        *,
        channel: str = "",
        chat_id: str = "",
        account_id: str = "",
        chat_type: str = "",
        message_thread_id: str = "",
    ) -> InterruptResult: ...
