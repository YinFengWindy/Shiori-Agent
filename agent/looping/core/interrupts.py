"""AgentLoop 中断状态与续跑控制。"""

from __future__ import annotations

import time
from dataclasses import replace
from ..interrupt import (
    InterruptResult,
    TurnInterruptState,
)
from bus.events import (
    InboundItem,
    InboundMessage,
    SpawnCompletionItem,
)
from bus.events_lifecycle import (
    TurnStarted,
)
from bus.queue import MessageBus

from .helpers import (
    _build_resume_content,
    _item_content,
    logger,
)

class _InterruptMixin:
    def request_interrupt(
        self,
        session_key: str,
        sender: str = "",
        command: str = "/stop",
    ) -> InterruptResult:
        """Channel 层调用的中断入口，不走 MessageBus。"""
        task = self._active_tasks.get(session_key)
        if task is None or task.done():
            return InterruptResult(
                status="idle",
                session_key=session_key,
                message="当前没有正在执行的任务。",
            )

        # 保存中断态（纯内存，不落库）
        active_state = self._active_turn_states.get(session_key)
        if active_state is None:
            active_state = TurnInterruptState(
                session_key=session_key,
                original_user_message="",
            )
        self._interrupt_states[session_key] = replace(
            active_state,
            interrupted_by=command,
            interrupted_at=time.monotonic(),
        )
        task.cancel()
        logger.info(
            f"Turn interrupted  session_key={session_key}  "
            f"sender={sender}  command={command}"
        )
        return InterruptResult(
            status="interrupted",
            session_key=session_key,
            message="本轮已中断。你可以继续补充要求，我会接着这件事处理。",
        )

    def _get_interrupt_state(self, session_key: str) -> TurnInterruptState | None:
        """读取中断态（含 TTL 过期检查），不提前消费。"""
        state = self._interrupt_states.get(session_key)
        if state is None:
            return None
        if state.expired:
            logger.info(f"Interrupt state expired for {session_key}, discarding")
            self._interrupt_states.pop(session_key, None)
            return None
        return state

    def _build_initial_turn_state(
        self,
        item: InboundItem,
        key: str,
    ) -> TurnInterruptState:
        # 1. 普通消息保留真实用户输入，spawn 回传用固定 marker 表示内部工作项。
        match item:
            case InboundMessage():
                return TurnInterruptState(
                    session_key=key,
                    original_user_message=item.content,
                    original_metadata=dict(item.metadata or {}),
                )
            case SpawnCompletionItem():
                return TurnInterruptState(
                    session_key=key,
                    original_user_message=_item_content(item),
                    original_metadata={},
                )
        raise TypeError(f"unsupported inbound item: {type(item).__name__}")

    def _resume_interrupted_message(
        self,
        msg: InboundItem,
        key: str,
    ) -> tuple[InboundItem, bool]:
        # 1. 只有普通入站消息参与续跑，内部工作项不消费中断态。
        if not isinstance(msg, InboundMessage):
            return msg, False
        interrupted = self._get_interrupt_state(key)
        if interrupted is None:
            return msg, False

        # 2. 有中断态时，把上一轮进度和本轮补充拼成新的用户消息。
        resumed = InboundMessage(
            channel=msg.channel,
            sender=msg.sender,
            chat_id=msg.chat_id,
            content=_build_resume_content(interrupted, msg.content),
            timestamp=msg.timestamp,
            media=msg.media,
            metadata={**(msg.metadata or {}), "resumed_from_interrupt": True},
        )
        logger.info(f"Resuming interrupted turn for {key}")
        self._active_turn_states[key] = TurnInterruptState(
            session_key=key,
            original_user_message=resumed.content,
            original_metadata=dict(resumed.metadata or {}),
        )
        return resumed, True

    async def _observe_turn_started(
        self,
        msg: InboundItem,
        key: str,
    ) -> None:
        # 1. 对外发布被动 turn 开始事件，具体副作用由 observer 决定。
        await self._event_bus.observe(
            TurnStarted(
                session_key=key,
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=_item_content(msg),
                timestamp=msg.timestamp,
            )
        )
