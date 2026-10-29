from __future__ import annotations
from shiori_sdk.messages import InboundMessage

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from contextlib import nullcontext
from typing import Any, Protocol

from agent.looping.core import AgentLoop
from agent.looping.interrupt import TurnInterruptState, current_tracking_key
from agent.turns.reply_interruption import (
    ReplyInterruption,
    reply_interruption_scope,
    current_reply_interruption,
)
from bus.event_bus import EventBus
from conversation.service import desktop_thread_id
from bus.events_lifecycle import ReplyMessageCommitted, TurnFailed
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
from desktop_bridge.chat_turn_state import (
    DEFERRED_CHAT_METHODS,
    DesktopChatTurn,
    EventEmitter,
    complete_despite_cancellation,
)
from desktop_bridge.turn_messages import committed_turn_messages
from desktop_bridge.tool_call_preview import truncate_desktop_tool_result
from session.manager import Session, SessionManager
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY
from shiori_sdk.errors import public_validation_message, summarize_exception_for_user
from core.roles.models import RoleRecord
from core.roles.reply_policy import natural_chat_selected
from core.roles.self_initializer import SelfInitializationError
from core.roles.model_errors import ModelConfigurationError
from core.common.runtime_tasks import create_runtime_task
from core.common.runtime_scope import current_runtime_lease

logger = logging.getLogger("desktop.bridge.chat")


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


class DesktopChatService:
    """Runs desktop chat turns and bridges lifecycle events back to the bridge stream."""

    def __init__(
        self,
        *,
        agent_loop: AgentLoop,
        event_bus: EventBus,
        session_manager: SessionManager,
        role_lookup: Callable[[str], RoleRecord | None],
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
        self._role_lookup = role_lookup
        self._role_id_from_session_key = role_id_from_session_key
        self._sync_desktop_session_thread = sync_desktop_session_thread
        self._emit_payload = emit_payload
        self._emit_session_updated = emit_session_updated
        self._streaming_enabled = bool(streaming_enabled)
        self._tasks_by_session: dict[str, DesktopChatTurn] = {}
        self._turns: set[DesktopChatTurn] = set()

    def is_busy(self, session_key: str) -> bool:
        """Returns whether the session already has an active desktop turn."""

        turn = self._tasks_by_session.get(session_key)
        return turn is not None and not turn.completed and not turn.task.done()

    def owns_chat_turn(self, session_key: str, turn_id: str | None = None) -> bool:
        """Whether this service actually owns the active turn, never a borrowed alias.

        The optional ID routes control requests to their original runtime.
        Admission can omit it to find this generation's latest accepted turn.
        """
        turn = self._tasks_by_session.get(session_key)
        return (
            turn is not None
            and turn in self._turns
            and self.is_busy(session_key)
            and (turn_id is None or turn.turn_id == turn_id)
        )

    def can_supersede_chat_turn(self, session_key: str) -> bool:
        """Whether the current owned or borrowed predecessor accepts supplements."""
        turn = self._tasks_by_session.get(session_key)
        return turn is not None and turn.reply_interruption is not None

    def supersede_chat_turn(self, session_key: str) -> None:
        """Invalidate before intake; the next runner waits for safe cleanup.

        Do not await a model/tool in the RPC mutation lane. The user input is
        acknowledged promptly and each accepted runner keeps its own identity.
        """
        turn = self._tasks_by_session.get(session_key)
        # Admission must fail before the handler persists a supplement when
        # busy work has no owner capable of accepting the handoff.
        if self.is_busy(session_key) and (
            turn is None or turn.reply_interruption is None
        ):
            raise ChatTurnBusyError("当前会话已有正在执行的聊天任务")
        if (
            self.is_busy(session_key)
            and turn is not None
            and turn.reply_interruption is not None
        ):
            turn.reply_interruption.invalidate()
        lease = current_runtime_lease()
        if lease is not None:
            lease.reply_sequences.interrupt_background(
                self._desktop_origin(session_key)
            )

    def _desktop_origin(self, session_key: str) -> InboundMessage:
        session = self._session_manager.get_or_create(session_key)
        return InboundMessage(
            channel="desktop",
            chat_id=session_key,
            sender="user",
            content="",
            metadata={
                "role_id": session.metadata.get("role_id"),
                "chat_type": "private",
            },
        )

    def continue_chat_after(self, session_key: str, owner: DesktopChatService) -> None:
        """Chain a new generation's input after the exact old desktop owner.

        The old service retains execution/cleanup ownership. This service only
        borrows its predecessor identity until a new input is accepted; invalid
        requests never invalidate it and RPC admission never waits for it.
        """
        if self.owns_chat_turn(session_key) or not owner.owns_chat_turn(session_key):
            return
        turn = owner._tasks_by_session.get(session_key)
        if turn is not None and self._tasks_by_session.get(session_key) is not turn:
            self._tasks_by_session[session_key] = turn
            turn.task.add_done_callback(
                lambda done: self._discard_task(session_key, done)
            )

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
        if active_turn is None or not self.owns_chat_turn(normalized_session_key):
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

        # The turn's own runner persists the interrupted reply and publishes it.
        return self._prepare_cancel(
            normalized_session_key,
            normalized_turn_id=normalized_turn_id,
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
        if active_turn is None or not self.owns_chat_turn(normalized_session_key):
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
        result = self._prepare_cancel(
            normalized_session_key,
            normalized_turn_id=normalized_turn_id,
        )
        await self._await_turn_cleanup(normalized_session_key, active_turn)
        if active_turn.interrupted_message is not None:
            # The renderer must swap its transient trace for the persisted
            # message, or the next turn sorts around an id-less bubble.
            result = replace(
                result,
                session=self._session_manager.get_or_create(normalized_session_key),
                interrupted_message=active_turn.interrupted_message,
            )
        return result

    def _prepare_cancel(
        self,
        session_key: str,
        normalized_turn_id: str | None = None,
    ) -> ChatTurnCancelResult:
        """Stops renderer-owned work and hands its interrupt snapshot to the turn."""

        active_turn = self._tasks_by_session.get(session_key)
        turn_id = normalized_turn_id or (active_turn.turn_id if active_turn else "")
        if active_turn is not None and not active_turn.started:
            # The loop still belongs to its predecessor. Cancelling a queued
            # input may only cancel that input's wrapper, never the older tool.
            active_turn.cancel_requested = True
            return ChatTurnCancelResult(
                "interrupted", session_key, turn_id, "已中止当前回合"
            )
        raw_result = self._agent_loop.request_interrupt(
            session_key,
            sender="desktop",
            command="/cancel",
        )
        interrupt_state = getattr(raw_result, "state", None)
        # Keep a naturally completed wrapper alive when AgentLoop reports idle;
        # it still needs to publish its final session update.
        if active_turn is not None and raw_result.status == "interrupted":
            if active_turn.finished:
                # Already publishing done / error: nothing is left to interrupt.
                if isinstance(interrupt_state, TurnInterruptState):
                    self._discard_interrupt_state(session_key, interrupt_state)
            else:
                if isinstance(interrupt_state, TurnInterruptState):
                    active_turn.interrupt_state = interrupt_state
                _ = active_turn.task.cancel()
        return ChatTurnCancelResult(
            status=str(getattr(raw_result, "status", "interrupted")),
            session_key=session_key,
            turn_id=turn_id,
            message=(
                raw_result.message
                if raw_result.status == "interrupted"
                else "已中止当前回合"
            ),
        )

    async def _await_turn_cleanup(
        self,
        session_key: str,
        active_turn: DesktopChatTurn,
    ) -> None:
        try:
            await active_turn.task
        except asyncio.CancelledError:
            pass
        # Absorb only the turn's own cancellation. A cancelled caller (shutdown,
        # a cancelled RPC) must still stop, even when its cancel was forwarded
        # into the turn and the turn ended quietly.
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise asyncio.CancelledError
        # A turn cancelled before its first step never ran its runner; its
        # terminal comes from the late finisher, or from here if the task's
        # done callback has not run yet (the claim makes either one a no-op).
        if active_turn.late_finisher is not None:
            await active_turn.late_finisher
        elif not active_turn.finished:
            await self._finish_turn(active_turn, cancelled=True)
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
        interruption = current_reply_interruption()

        async def _on_delta(event: StreamDeltaReady) -> None:
            if event.session_key != session_key or event.channel != "desktop":
                return
            if interruption is not None:
                if interruption.invalidated:
                    return
                interruption.record_visible_delta(
                    event.content_delta, event.thinking_delta
                )
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
            if (
                event.session_key != session_key
                or event.channel != "desktop"
                or (event.request_id and event.request_id != request_id)
            ):
                return
            # Later lifecycle modules and session synchronization can still fail.
            # Resolve the terminal event only after all awaited turn work succeeds.
            committed = event

        async def _on_message(event: ReplyMessageCommitted) -> None:
            if event.session_key != session_key or event.turn_id != turn_id:
                return
            session = self._session_manager.get_or_create(session_key)
            ids = set(event.message_ids)

            async def publish(payload: dict[str, Any]) -> None:
                # An intermediate message is visible immediately. The ordinary
                # terminal session.updated still waits for role ownership release.
                await self._emit_payload(
                    emit_event,
                    {
                        **payload,
                        "method": "chat.message",
                        "payload": {**payload["payload"], "turn_id": turn_id},
                    },
                )

            await self._emit_session_updated(
                request_id=request_id,
                session=session,
                emit_event=publish,
                messages=[row for row in session.messages if row.get("id") in ids],
            )

        async def _on_failed(event: TurnFailed) -> None:
            nonlocal failure_detail
            if (
                event.session_key == session_key
                and current_tracking_key(session_key) == session_key
            ):
                failure_detail = event.error_summary

        async def _on_tool_started(event: ToolCallStarted) -> None:
            if event.session_key != session_key or event.channel != "desktop":
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
            if event.session_key != session_key or event.channel != "desktop":
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
        self._event_bus.on(ReplyMessageCommitted, _on_message)
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
            self._event_bus.off(ReplyMessageCommitted, _on_message)
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
        admission_lease = current_runtime_lease()
        background = (
            admission_lease.reply_sequences.background_tasks(
                self._desktop_origin(session_key)
            )
            if admission_lease is not None
            else ()
        )
        previous = self._tasks_by_session.get(session_key)
        if self.is_busy(session_key):
            if (
                previous is None
                or previous.reply_interruption is None
                or not previous.reply_interruption.invalidated
            ):
                raise ChatTurnBusyError(f"会话 {session_key} 已有正在执行的聊天任务")

        turn = DesktopChatTurn(
            request_id=request_id,
            turn_id=turn_id,
            session_key=session_key,
            emit_event=emit_event,
            previous=previous,
            reply_interruption=ReplyInterruption(
                natural_chat=natural_chat_selected(
                    self._role_lookup(self._role_id_from_session_key(session_key))
                )
            ),
        )

        async def emit_turn_event(payload: dict[str, Any]) -> None:
            if payload.get("method") == "session.updated":
                payload = {
                    **payload,
                    "payload": {**payload["payload"], "turn_id": turn_id},
                }
            # Completion enables the next send in the renderer. Publish it only
            # after the role turn and persistence have released their ownership.
            if turn.deferred_events or payload.get("method") in DEFERRED_CHAT_METHODS:
                turn.deferred_events.append(payload)
            else:
                await self._emit_payload(emit_event, payload)

        async def _runner() -> None:
            cancelled = False
            try:
                if background:
                    await asyncio.shield(
                        asyncio.gather(*background, return_exceptions=True)
                    )
                if previous is not None:
                    # Cancellation of this queued request cannot cancel a tool
                    # still finishing in the preceding request.
                    await asyncio.shield(
                        asyncio.gather(previous.task, return_exceptions=True)
                    )
                    if previous.late_finisher is not None:
                        await asyncio.shield(previous.late_finisher)
                if turn.cancel_requested:
                    raise asyncio.CancelledError
                lease = current_runtime_lease()
                turn.started = True
                with (
                    reply_interruption_scope(turn.reply_interruption),
                    (
                        lease.reply_sequences.track(turn.reply_interruption)
                        if lease is not None
                        else nullcontext()
                    ),
                ):
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
                cancelled = True
            except Exception:
                logger.exception("desktop chat turn failed: %s", session_key)
            finally:
                await self._finish_turn(turn, cancelled=cancelled)

        turn.task = create_runtime_task(_runner(), name=f"desktop-chat:{session_key}")
        self._tasks_by_session[session_key] = turn
        self._turns.add(turn)
        turn.task.add_done_callback(lambda _task: self._on_turn_task_done(turn))

    def _on_turn_task_done(self, turn: DesktopChatTurn) -> None:
        self._turns.discard(turn)
        if not turn.finished:
            # Cancelled before its first step: the runner never ran, so the
            # terminal is published by a follow-up task that cleanup awaits.
            turn.late_finisher = create_runtime_task(
                self._finish_turn(turn, cancelled=True),
                name=f"desktop-chat-terminal:{turn.session_key}",
            )
        self._discard_task(turn.session_key, turn.task)

    async def _finish_turn(self, turn: DesktopChatTurn, *, cancelled: bool) -> None:
        """Publishes exactly one terminal event for ``turn``, shielded from shutdown.

        A cancelled turn that has not already resolved to chat.done / chat.error
        first persists its interrupted reply (when a turn-id cancel supplied
        one), announces it with ``session.updated`` and then ends with
        ``chat.cancelled``.

        A failed persistence still ends the turn with ``chat.cancelled`` and
        then propagates.
        """

        if turn.finished:
            return
        turn.finished = True
        if turn.previous is not None:
            # Even a wrapper cancelled before its first step stays behind its
            # predecessor. A later supplement cannot overtake active tools.
            await complete_despite_cancellation(
                asyncio.gather(turn.previous.task, return_exceptions=True)
            )
            if turn.previous.late_finisher is not None:
                await complete_despite_cancellation(turn.previous.late_finisher)
        state, turn.interrupt_state = turn.interrupt_state, None
        try:
            if cancelled and not turn.has_terminal():
                try:
                    if state is not None:
                        await complete_despite_cancellation(
                            self._publish_interrupted_turn(turn, state)
                        )
                finally:
                    turn.deferred_events.append(
                        build_chat_cancelled_event(
                            request_id=turn.request_id,
                            turn_id=turn.turn_id,
                            session_key=turn.session_key,
                        ).to_dict()
                    )
            elif state is not None:
                self._discard_interrupt_state(turn.session_key, state)
        finally:
            turn.completed = True
            await complete_despite_cancellation(self._flush_deferred_events(turn))

    async def _publish_interrupted_turn(
        self,
        turn: DesktopChatTurn,
        state: TurnInterruptState,
    ) -> None:
        """Persists a cancelled reply and queues the session update announcing it."""

        try:
            turn.interrupted_message = await self._persist_interrupted_turn(
                session_key=turn.session_key,
                turn_id=turn.turn_id,
                state=state,
            )
        finally:
            self._discard_interrupt_state(turn.session_key, state)
        await self._emit_session_updated(
            request_id=turn.request_id,
            session=self._session_manager.get_or_create(turn.session_key),
            emit_event=turn.deferred_events.append,
            messages=(
                [turn.interrupted_message]
                if turn.interrupted_message is not None
                else None
            ),
        )

    def _discard_interrupt_state(
        self, session_key: str, state: TurnInterruptState
    ) -> None:
        discard = getattr(self._agent_loop, "discard_interrupt_state", None)
        if callable(discard):
            discard(session_key, state)

    async def _flush_deferred_events(self, turn: DesktopChatTurn) -> None:
        for event in turn.deferred_events:
            await self._emit_payload(turn.emit_event, event)

    async def aclose(self) -> None:
        """Cancels and awaits every desktop-owned chat turn."""

        turns = list(self._turns)
        for turn in turns:
            if not turn.task.done():
                if turn.started:
                    _ = turn.task.cancel()
                else:
                    turn.cancel_requested = True
        if turns:
            _ = await asyncio.gather(
                *(self._await_turn_cleanup(turn.session_key, turn) for turn in turns),
                return_exceptions=True,
            )
        self._tasks_by_session.clear()
        self._turns.clear()

    async def drain(self) -> None:
        """Waits for accepted chat turns without cancelling them."""
        while self._turns:
            tasks = [turn.task for turn in self._turns]
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
