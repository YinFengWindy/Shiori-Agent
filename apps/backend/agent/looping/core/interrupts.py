"""AgentLoop 中断状态与续跑控制。"""

from __future__ import annotations

import time
from dataclasses import replace
from ..interrupt import (
    InterruptResult,
    TurnInterruptState,
    in_detached_turn,
    turn_tracking_key,
    current_tracking_key,
)
from bus.events import InboundItem, SpawnCompletionItem
from shiori_sdk.messages import InboundMessage
from shiori_sdk.channel_events import TurnCancelled, TurnStarted

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
        *,
        channel: str = "",
        chat_id: str = "",
        account_id: str = "",
        chat_type: str = "",
        message_thread_id: str = "",
    ) -> InterruptResult:
        """Channel 层调用的中断入口，不走 MessageBus。"""
        try:
            key = turn_tracking_key(
                session_key,
                channel,
                chat_id,
                account_id=account_id,
                chat_type=chat_type,
                message_thread_id=message_thread_id,
            )
        except ValueError:
            key = None
        # Session-only legacy callers may stop sole legacy work. Never infer
        # an account/topic from a shared role session or a partial chat address.
        if key not in self._active_tasks and not any(
            (channel, chat_id, account_id, chat_type, message_thread_id)
        ):
            matches = [
                k
                for k, state in self._active_turn_states.items()
                if state.session_key == session_key
                and not any(
                    state.original_metadata.get(field)
                    for field in ("account_id", "chat_type", "message_thread_id")
                )
            ]
            if len(matches) == 1:
                key = matches[0]
        task = self._active_tasks.get(key) if key is not None else None
        if task is None or task.done():
            return InterruptResult(
                status="idle",
                session_key=session_key,
                message="当前没有正在执行的任务。",
            )

        assert key is not None
        # 保存中断态（纯内存，不落库）
        active_state = self._active_turn_states.get(key)
        if active_state is None:
            active_state = TurnInterruptState(
                session_key=session_key,
                original_user_message="",
            )
        snapshot = replace(
            active_state,
            original_metadata=dict(active_state.original_metadata),
            tools_used=list(active_state.tools_used),
            tool_chain_partial=list(active_state.tool_chain_partial),
            interrupted_by=command,
            interrupted_at=time.monotonic(),
        )
        self._interrupt_states[key] = snapshot
        task.cancel()
        logger.info(
            f"Turn interrupted  session_key={session_key}  "
            f"sender={sender}  command={command}"
        )
        return InterruptResult(
            status="interrupted",
            session_key=session_key,
            message="本轮已中断。你可以继续补充要求，我会接着这件事处理。",
            state=snapshot,
        )

    def discard_interrupt_state(
        self,
        session_key: str,
        state: TurnInterruptState,
    ) -> None:
        """Drops a snapshot after its channel has durably persisted it."""

        for key, value in tuple(self._interrupt_states.items()):
            if value is state:
                self._interrupt_states.pop(key)

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
        # Desktop persists the partial assistant trace and exposes the interruption
        # as a separate session context frame; never duplicate it in user content.
        # A detached external turn never resumes another turn's interruption.
        if msg.channel == "desktop" or in_detached_turn():
            return msg, False
        tracking_key = current_tracking_key(key)
        interrupted = self._get_interrupt_state(tracking_key)
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
        self._active_turn_states[tracking_key] = TurnInterruptState(
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
                external_message_id=str(
                    getattr(msg, "metadata", {}).get("external_message_id") or ""
                ),
            )
        )

    async def _observe_turn_cancelled(self, msg: InboundItem, key: str) -> None:
        await self._event_bus.observe(
            TurnCancelled(
                session_key=key,
                channel=msg.channel,
                chat_id=msg.chat_id,
                external_message_id=str(
                    getattr(msg, "metadata", {}).get("external_message_id") or ""
                ),
            )
        )
