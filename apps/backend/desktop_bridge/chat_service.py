from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from agent.looping.core import AgentLoop
from agent.looping.interrupt import TurnInterruptState
from bus.event_bus import EventBus
from conversation.service import desktop_thread_id
from bus.events_lifecycle import TurnFailed
from shiori_sdk.channel_events import (
    StreamDeltaReady,
    ToolCallCompleted,
    ToolCallStarted,
)
from shiori_sdk.memory.committed import TurnCommitted
from shiori_sdk.bridge import BridgeEvent
from desktop_bridge.chat_completion import (
    build_chat_cancelled_event,
    build_chat_terminal_event,
)
from desktop_bridge.turn_messages import committed_turn_messages
from desktop_bridge.tool_call_preview import truncate_desktop_tool_result
from session.manager import Session, SessionManager
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY
from shiori_sdk.errors import public_validation_message, summarize_exception_for_user
from core.roles.self_initializer import SelfInitializationError
from core.roles.model_errors import ModelConfigurationError
from core.common.runtime_tasks import create_runtime_task

logger = logging.getLogger("desktop.bridge.chat")

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]

# Every started desktop turn ends with exactly one of these events.
_TERMINAL_CHAT_METHODS = frozenset({"chat.done", "chat.error", "chat.cancelled"})


class SyncDesktopSessionThread(Protocol):
    """Synchronizes a desktop session with its role-owned thread."""

    def __call__(self, session: Session, *, role_id: str) -> None: ...


class EmitSessionUpdated(Protocol):
    """Emits a serialized session update through one bridge connection."""

    async def __call__(
        self,
        *,
        request_id: str,
        session: Session,
        emit_event: EventEmitter,
        messages: list[dict[str, Any]] | None = None,
    ) -> None: ...


class ChatTurnBusyError(RuntimeError):
    """Raised when a desktop session already owns an active chat turn."""


@dataclass(frozen=True)
class ChatTurnCancelResult:
    """Result of a session-scoped desktop chat cancellation request."""

    status: str
    session_key: str
    turn_id: str
    message: str
    session: Session | None = None
    interrupted_message: dict[str, Any] | None = None


@dataclass(frozen=True)
class _DesktopChatTurn:
    """Tracks one renderer-owned turn without sharing state across sessions."""

    task: asyncio.Task[None]
    turn_id: str
    completed: bool = False


class DesktopChatService:
    """Runs desktop chat turns and bridges lifecycle events back to the bridge stream."""

    def __init__(
        self,
        *,
        agent_loop: AgentLoop,
        event_bus: EventBus,
        session_manager: SessionManager,
        role_id_from_session_key: Callable[[str], str],
        sync_desktop_session_thread: SyncDesktopSessionThread,
        emit_payload: Callable[
            [EventEmitter, dict[str, Any]],
            Awaitable[None],
        ],
        emit_session_updated: EmitSessionUpdated,
        streaming_enabled: bool = True,
    ) -> None:
        self._agent_loop = agent_loop
        self._event_bus = event_bus
        self._session_manager = session_manager
        self._role_id_from_session_key = role_id_from_session_key
        self._sync_desktop_session_thread = sync_desktop_session_thread
        self._emit_payload = emit_payload
        self._emit_session_updated = emit_session_updated
        self._streaming_enabled = bool(streaming_enabled)
        self._tasks_by_session: dict[str, _DesktopChatTurn] = {}

    def is_busy(self, session_key: str) -> bool:
        """Returns whether the session already has an active desktop turn."""

        turn = self._tasks_by_session.get(session_key)
        return turn is not None and not turn.completed and not turn.task.done()

    def cancel_chat_turn(
        self,
        session_key: str,
        turn_id: str,
    ) -> ChatTurnCancelResult:
        """Interrupts exactly one active renderer chat turn when its identity matches."""

        normalized_session_key = session_key.strip()
        normalized_turn_id = turn_id.strip()
        if not normalized_session_key or not normalized_turn_id:
            raise ValueError("session_key 和 turn_id 不能为空")
        active_turn = self._tasks_by_session.get(normalized_session_key)
        if active_turn is None or active_turn.task.done():
            return ChatTurnCancelResult(
                status="idle",
                session_key=normalized_session_key,
                turn_id=normalized_turn_id,
                message="当前回合已经结束",
            )
        if active_turn.turn_id != normalized_turn_id:
            return ChatTurnCancelResult(
                status="mismatch",
                session_key=normalized_session_key,
                turn_id=normalized_turn_id,
                message="当前会话正在执行另一个回合",
            )

        result, interrupt_state = self._prepare_cancel(
            normalized_session_key,
        )
        self._schedule_interrupted_persistence(
            session_key=normalized_session_key,
            turn_id=normalized_turn_id,
            state=interrupt_state,
            task=active_turn.task,
        )
        return ChatTurnCancelResult(
            status=result.status,
            session_key=normalized_session_key,
            turn_id=normalized_turn_id,
            message=result.message,
        )

    async def cancel_chat_turn_async(
        self,
        session_key: str,
        turn_id: str,
    ) -> ChatTurnCancelResult:
        """Cancels a turn and waits for its partial reply to be durable."""

        normalized_session_key = session_key.strip()
        normalized_turn_id = turn_id.strip()
        if not normalized_session_key or not normalized_turn_id:
            raise ValueError("session_key 和 turn_id 不能为空")
        active_turn = self._tasks_by_session.get(normalized_session_key)
        if active_turn is None or active_turn.task.done():
            return ChatTurnCancelResult(
                status="idle",
                session_key=normalized_session_key,
                turn_id=normalized_turn_id,
                message="当前回合已经结束",
            )
        if active_turn.turn_id != normalized_turn_id:
            return ChatTurnCancelResult(
                status="mismatch",
                session_key=normalized_session_key,
                turn_id=normalized_turn_id,
                message="当前会话正在执行另一个回合",
            )
        result, interrupt_state = self._prepare_cancel(
            normalized_session_key,
            normalized_turn_id=normalized_turn_id,
        )
        if active_turn is not None:
            await self._await_turn_cleanup(normalized_session_key, active_turn)
        if result.status == "interrupted" and isinstance(
            interrupt_state, TurnInterruptState
        ):
            interrupted_message = await self._persist_interrupted_turn(
                session_key=normalized_session_key,
                turn_id=normalized_turn_id,
                state=interrupt_state,
            )
            discard = getattr(self._agent_loop, "discard_interrupt_state", None)
            if callable(discard):
                discard(normalized_session_key, interrupt_state)
            if interrupted_message is not None:
                # The renderer must swap its transient trace for the persisted
                # message, or the next turn sorts around an id-less bubble.
                result = replace(
                    result,
                    session=self._session_manager.get_or_create(normalized_session_key),
                    interrupted_message=interrupted_message,
                )
        return result

    async def _persist_and_discard_interrupted_turn(
        self,
        *,
        session_key: str,
        turn_id: str,
        state: TurnInterruptState,
    ) -> None:
        await self._persist_interrupted_turn(
            session_key=session_key,
            turn_id=turn_id,
            state=state,
        )
        discard = getattr(self._agent_loop, "discard_interrupt_state", None)
        if callable(discard):
            discard(session_key, state)

    def _schedule_interrupted_persistence(
        self,
        *,
        session_key: str,
        turn_id: str,
        state: TurnInterruptState | None,
        task: asyncio.Task[None] | None = None,
    ) -> None:
        """Schedules compatibility-path persistence when no async caller can await it."""

        if state is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            self._persist_after_turn_cleanup(
                session_key=session_key,
                turn_id=turn_id,
                state=state,
                task=task,
            )
        )

    async def _persist_after_turn_cleanup(
        self,
        *,
        session_key: str,
        turn_id: str,
        state: TurnInterruptState,
        task: asyncio.Task[None] | None,
    ) -> None:
        if task is not None:
            active_turn = self._tasks_by_session.get(session_key)
            if active_turn is not None and active_turn.task is task:
                await self._await_turn_cleanup(session_key, active_turn)
        await self._persist_and_discard_interrupted_turn(
            session_key=session_key,
            turn_id=turn_id,
            state=state,
        )

    def _prepare_cancel(
        self,
        session_key: str,
        normalized_turn_id: str | None = None,
    ) -> tuple[ChatTurnCancelResult, TurnInterruptState | None]:
        """Stops renderer-owned work and returns the immutable interrupt snapshot."""

        active_turn = self._tasks_by_session.get(session_key)
        turn_id = normalized_turn_id or (active_turn.turn_id if active_turn else "")
        raw_result = self._agent_loop.request_interrupt(
            session_key,
            sender="desktop",
            command="/cancel",
        )
        interrupt_state = getattr(raw_result, "state", None)
        # Keep a naturally completed wrapper alive when AgentLoop reports idle;
        # it still needs to publish its final session update.
        if active_turn is not None and raw_result.status == "interrupted":
            _ = active_turn.task.cancel()
        return (
            ChatTurnCancelResult(
                status=str(getattr(raw_result, "status", "interrupted")),
                session_key=session_key,
                turn_id=turn_id,
                message=(
                    raw_result.message
                    if raw_result.status == "interrupted"
                    else "已中止当前回合"
                ),
            ),
            (
                interrupt_state
                if isinstance(interrupt_state, TurnInterruptState)
                else None
            ),
        )

    async def _await_turn_cleanup(
        self,
        session_key: str,
        active_turn: _DesktopChatTurn,
    ) -> None:
        try:
            await active_turn.task
        except asyncio.CancelledError:
            pass
        self._discard_task(session_key, active_turn.task)

    async def _persist_interrupted_turn(
        self,
        *,
        session_key: str,
        turn_id: str,
        state: TurnInterruptState,
    ) -> dict[str, Any] | None:
        """Persists one cancelled desktop reply before its session can be reused."""

        session = self._session_manager.get_or_create(session_key)
        if self._has_completed_turn(session, turn_id):
            return None
        has_trace = bool(
            state.partial_reply
            or state.partial_thinking
            or state.tools_used
            or state.tool_chain_partial
        )
        role_id = self._role_id_from_session_key(session_key)
        assistant_metadata: dict[str, Any] = {
            "interrupted_reply": True,
            "turn_id": turn_id,
            "interrupted_by": state.interrupted_by,
        }
        if role_id:
            # 中断的回复属于桌面会话，按会话划分上下文时才能被归入用户上下文。
            assistant_metadata["thread_id"] = desktop_thread_id(role_id)
        assistant_kwargs: dict[str, Any] = {
            "metadata": assistant_metadata,
            "tools_used": list(state.tools_used) if state.tools_used else None,
            "tool_chain": (
                list(state.tool_chain_partial) if state.tool_chain_partial else None
            ),
        }
        if state.partial_thinking is not None:
            assistant_kwargs["reasoning_content"] = state.partial_thinking
        assistant_message: dict[str, Any] | None = None
        if has_trace:
            session.add_message("assistant", state.partial_reply, **assistant_kwargs)
            assistant_message = session.messages[-1]
        session.metadata[INTERRUPTED_TURN_METADATA_KEY] = {
            "turn_id": turn_id,
            "interrupted_by": state.interrupted_by,
        }
        await self._session_manager.append_messages(
            session,
            [assistant_message] if assistant_message is not None else [],
        )
        if role_id:
            self._sync_desktop_session_thread(session, role_id=role_id)
        return assistant_message

    @staticmethod
    def _has_completed_turn(session: Session, turn_id: str) -> bool:
        for message in reversed(session.messages):
            if message.get("role") != "assistant":
                continue
            metadata = message.get("metadata")
            if not isinstance(metadata, dict):
                continue
            if metadata.get("turn_id") != turn_id:
                continue
            return True
        return False

    async def run_chat_turn(
        self,
        *,
        request_id: str,
        session_key: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
        omit_user_turn: bool,
        emit_event: EventEmitter,
        turn_id: str | None = None,
    ) -> tuple[Session, list[BridgeEvent]]:
        turn_id = turn_id or request_id
        collected: list[BridgeEvent] = []
        committed: TurnCommitted | None = None
        failure_detail = ""

        async def _on_delta(event: StreamDeltaReady) -> None:
            if event.session_key != session_key:
                return
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.delta",
                payload={
                    "session_key": event.session_key,
                    "turn_id": turn_id,
                    "content_delta": event.content_delta,
                    "thinking_delta": event.thinking_delta,
                },
            )
            collected.append(bridge_event)
            await self._emit_payload(emit_event, bridge_event.to_dict())

        async def _on_done(event: TurnCommitted) -> None:
            nonlocal committed
            if event.session_key != session_key:
                return
            # Later lifecycle modules and session synchronization can still fail.
            # Resolve the terminal event only after all awaited turn work succeeds.
            committed = event

        async def _on_failed(event: TurnFailed) -> None:
            nonlocal failure_detail
            if event.session_key == session_key:
                failure_detail = event.error_summary

        async def _on_tool_started(event: ToolCallStarted) -> None:
            if event.session_key != session_key:
                return
            call_id = str(event.call_id or "").strip()
            tool_name = str(event.tool_name or "").strip()
            if not call_id or not tool_name:
                return
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.tool.started",
                payload={
                    "session_key": event.session_key,
                    "turn_id": turn_id,
                    "iteration": event.iteration,
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "arguments": dict(event.arguments),
                },
            )
            collected.append(bridge_event)
            await self._emit_payload(emit_event, bridge_event.to_dict())

        async def _on_tool_completed(event: ToolCallCompleted) -> None:
            if event.session_key != session_key:
                return
            call_id = str(event.call_id or "").strip()
            tool_name = str(event.tool_name or "").strip()
            if not call_id or not tool_name:
                return
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.tool.completed",
                payload={
                    "session_key": event.session_key,
                    "turn_id": turn_id,
                    "iteration": event.iteration,
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "arguments": dict(event.arguments),
                    "final_arguments": dict(event.final_arguments),
                    "status": event.status,
                    "result_preview": truncate_desktop_tool_result(
                        event.result_preview
                    ),
                },
            )
            collected.append(bridge_event)
            await self._emit_payload(emit_event, bridge_event.to_dict())

        self._event_bus.on(StreamDeltaReady, _on_delta)
        if self._streaming_enabled:
            self._event_bus.on(ToolCallStarted, _on_tool_started)
            self._event_bus.on(ToolCallCompleted, _on_tool_completed)
        self._event_bus.on(TurnCommitted, _on_done)
        self._event_bus.on(TurnFailed, _on_failed)
        try:
            reply = await self._agent_loop.process_direct(
                content,
                session_key=session_key,
                channel="desktop",
                chat_id=session_key,
                omit_user_turn=omit_user_turn,
                media=media,
                metadata=metadata,
                stream_events=self._streaming_enabled,
            )
            await asyncio.sleep(0)
            session = self._session_manager.get_or_create(session_key)
            role_id = self._role_id_from_session_key(session_key)
            if role_id:
                self._sync_desktop_session_thread(session, role_id=role_id)
            # Prepare the durable session update before reporting success, while
            # retaining chat.done -> session.updated ordering for the renderer.
            session_events: list[dict[str, Any]] = []
            await self._emit_session_updated(
                request_id=request_id,
                session=session,
                emit_event=session_events.append,
                messages=committed_turn_messages(session, committed),
            )
            bridge_event = build_chat_terminal_event(
                request_id=request_id,
                turn_id=turn_id,
                session_key=session_key,
                role_id=role_id,
                committed=committed,
                failure_message=reply,
                failure_detail=failure_detail,
            )
            collected.append(bridge_event)
            if bridge_event.method == "chat.done":
                await self._emit_payload(emit_event, bridge_event.to_dict())
            for event in session_events:
                await self._emit_payload(emit_event, event)
            if bridge_event.method == "chat.error":
                await self._emit_payload(emit_event, bridge_event.to_dict())
            return session, collected
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._emit_failed_session_update(
                request_id=request_id,
                session_key=session_key,
                emit_event=emit_event,
            )
            bridge_event = build_chat_terminal_event(
                request_id=request_id,
                turn_id=turn_id,
                session_key=session_key,
                role_id="",
                failure_message=(
                    public_validation_message(exc)
                    if isinstance(
                        exc, (SelfInitializationError, ModelConfigurationError)
                    )
                    else "这次回复未完成，请重试"
                ),
                failure_detail=summarize_exception_for_user(exc),
            )
            collected.append(bridge_event)
            await self._emit_payload(emit_event, bridge_event.to_dict())
            raise
        finally:
            self._event_bus.off(StreamDeltaReady, _on_delta)
            if self._streaming_enabled:
                self._event_bus.off(ToolCallStarted, _on_tool_started)
                self._event_bus.off(ToolCallCompleted, _on_tool_completed)
            self._event_bus.off(TurnCommitted, _on_done)
            self._event_bus.off(TurnFailed, _on_failed)

    async def _emit_failed_session_update(
        self,
        *,
        request_id: str,
        session_key: str,
        emit_event: EventEmitter,
    ) -> None:
        """Reconciles failed turns without replacing their original exception."""

        try:
            session_events: list[dict[str, Any]] = []
            await self._emit_session_updated(
                request_id=request_id,
                session=self._session_manager.get_or_create(session_key),
                emit_event=session_events.append,
            )
            for event in session_events:
                await self._emit_payload(emit_event, event)
        except Exception:
            # Snapshot preparation is secondary to delivering the terminal error.
            logger.exception("failed to publish failed-turn session: %s", session_key)

    def start_chat_turn(
        self,
        *,
        request_id: str,
        session_key: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
        omit_user_turn: bool,
        emit_event: EventEmitter,
        turn_id: str | None = None,
    ) -> None:
        turn_id = turn_id or request_id
        if self.is_busy(session_key):
            raise ChatTurnBusyError(f"会话 {session_key} 已有正在执行的聊天任务")

        terminal_events: list[dict[str, Any]] = []

        async def emit_turn_event(payload):
            # Completion enables the next send in the renderer. Publish it only
            # after the role turn and persistence have released their ownership.
            if terminal_events or payload.get("method") in {
                "chat.done",
                "chat.error",
                "session.updated",
            }:
                terminal_events.append(payload)
            else:
                await self._emit_payload(emit_event, payload)

        async def _runner() -> None:
            try:
                _ = await self.run_chat_turn(
                    request_id=request_id,
                    turn_id=turn_id,
                    session_key=session_key,
                    content=content,
                    media=media,
                    metadata=metadata,
                    omit_user_turn=omit_user_turn,
                    emit_event=emit_turn_event,
                )
            except asyncio.CancelledError:
                # A cancelled turn still ends with a terminal event, unless it
                # already resolved to chat.done / chat.error before the cancel.
                if not any(
                    event.get("method") in _TERMINAL_CHAT_METHODS
                    for event in terminal_events
                ):
                    terminal_events.append(
                        build_chat_cancelled_event(
                            request_id=request_id,
                            turn_id=turn_id,
                            session_key=session_key,
                        ).to_dict()
                    )
                return
            except Exception:
                logger.exception("desktop chat turn failed: %s", session_key)
            finally:
                owner = self._tasks_by_session.get(session_key)
                if owner is not None and owner.task is asyncio.current_task():
                    self._tasks_by_session[session_key] = replace(owner, completed=True)
                for event in terminal_events:
                    await self._emit_payload(emit_event, event)

        task = create_runtime_task(_runner(), name=f"desktop-chat:{session_key}")
        self._tasks_by_session[session_key] = _DesktopChatTurn(
            task=task,
            turn_id=turn_id,
        )
        task.add_done_callback(
            lambda completed, key=session_key: self._discard_task(
                key,
                completed,
            )
        )

    async def aclose(self) -> None:
        """Cancels and awaits every desktop-owned chat turn."""

        tasks = [turn.task for turn in self._tasks_by_session.values()]
        for task in tasks:
            if not task.done():
                _ = task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks_by_session.clear()

    async def drain(self) -> None:
        """Waits for accepted chat turns without cancelling them."""
        while self._tasks_by_session:
            tasks = [turn.task for turn in self._tasks_by_session.values()]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0)

    def _discard_task(
        self,
        session_key: str,
        task: asyncio.Task[None],
    ) -> None:
        active_turn = self._tasks_by_session.get(session_key)
        if active_turn is not None and active_turn.task is task:
            _ = self._tasks_by_session.pop(session_key, None)
