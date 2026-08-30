from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from agent.looping.core import AgentLoop
from agent.looping.interrupt import TurnInterruptState
from bus.event_bus import EventBus
from bus.events_lifecycle import (
    StreamDeltaReady,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCommitted,
)
from desktop_bridge.models import BridgeEvent
from desktop_bridge.voice.role_tts_settings import resolve_role_tts_settings
from desktop_bridge.tool_call_preview import truncate_desktop_tool_result
from desktop_bridge.voice.tts_coordinator import TtsTurnCoordinator
from desktop_bridge.voice.voice_service import VoiceService
from session.manager import Session, SessionManager
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY

logger = logging.getLogger("desktop.bridge.chat")

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]


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


@dataclass(frozen=True)
class _DesktopChatTurn:
    """Tracks one renderer-owned turn without sharing state across sessions."""

    task: asyncio.Task[None]
    turn_id: str
    voice_turn_id: str


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
        tts_service: VoiceService | None = None,
        streaming_enabled: bool = True,
    ) -> None:
        self._agent_loop = agent_loop
        self._event_bus = event_bus
        self._session_manager = session_manager
        self._role_id_from_session_key = role_id_from_session_key
        self._sync_desktop_session_thread = sync_desktop_session_thread
        self._emit_payload = emit_payload
        self._emit_session_updated = emit_session_updated
        self._tts_service = tts_service
        self._streaming_enabled = bool(streaming_enabled)
        self._tasks_by_session: dict[str, _DesktopChatTurn] = {}
        self._voice_turn_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}
        self._tts_tasks: set[asyncio.Task[None]] = set()
        self._tts_coordinators: dict[str, TtsTurnCoordinator] = {}

    def is_busy(self, session_key: str) -> bool:
        """Returns whether the session already has an active desktop turn."""

        turn = self._tasks_by_session.get(session_key)
        return turn is not None and not turn.task.done()

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
        )
        return ChatTurnCancelResult(
            status="interrupted",
            session_key=normalized_session_key,
            turn_id=normalized_turn_id,
            message=result.message if result.status == "interrupted" else "已中止当前回复",
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
        if result.status == "interrupted" and isinstance(
            interrupt_state, TurnInterruptState
        ):
            await self._persist_interrupted_turn(
                session_key=normalized_session_key,
                turn_id=normalized_turn_id,
                state=interrupt_state,
            )
            discard = getattr(self._agent_loop, "discard_interrupt_state", None)
            if callable(discard):
                discard(normalized_session_key, interrupt_state)
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
    ) -> None:
        """Schedules compatibility-path persistence when no async caller can await it."""

        if state is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            self._persist_and_discard_interrupted_turn(
                session_key=session_key,
                turn_id=turn_id,
                state=state,
            )
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
        active_turn.task.cancel() if active_turn is not None else None
        _ = self._tasks_by_session.pop(session_key, None)
        if active_turn is not None and active_turn.voice_turn_id and self._voice_turn_tasks.get(
            active_turn.voice_turn_id
        ) == (session_key, active_turn.task):
            _ = self._voice_turn_tasks.pop(active_turn.voice_turn_id, None)
        if active_turn is not None and active_turn.voice_turn_id:
            coordinator = self._tts_coordinators.pop(active_turn.voice_turn_id, None)
            if coordinator is not None:
                coordinator.cancel()
        return (
            ChatTurnCancelResult(
                status="interrupted",
                session_key=session_key,
                turn_id=turn_id,
                message=(
                    raw_result.message
                    if raw_result.status == "interrupted"
                    else "已中止当前回合"
                ),
            ),
            interrupt_state if isinstance(interrupt_state, TurnInterruptState) else None,
        )

    async def _persist_interrupted_turn(
        self,
        *,
        session_key: str,
        turn_id: str,
        state: TurnInterruptState,
    ) -> None:
        """Persists one cancelled desktop reply before its session can be reused."""

        session = self._session_manager.get_or_create(session_key)
        if self._has_completed_turn(session, turn_id):
            return
        has_trace = bool(
            state.partial_reply
            or state.partial_thinking
            or state.tools_used
            or state.tool_chain_partial
        )
        assistant_metadata = {
            "interrupted_reply": True,
            "turn_id": turn_id,
            "interrupted_by": state.interrupted_by,
        }
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
        role_id = self._role_id_from_session_key(session_key)
        if role_id:
            self._sync_desktop_session_thread(session, role_id=role_id)

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

    def cancel_voice_turn(self, turn_id: str) -> bool:
        """Cancels chat and synthesis work owned by one voice input turn."""

        normalized_turn_id = turn_id.strip()
        if not normalized_turn_id:
            return False
        cancelled = False
        owner = self._voice_turn_tasks.get(normalized_turn_id)
        if owner is not None:
            session_key, task = owner
            active_turn = self._tasks_by_session.get(session_key)
            if active_turn is not None and active_turn.task is task and not task.done():
                _, interrupt_state = self._prepare_cancel(
                    session_key,
                    normalized_turn_id=active_turn.turn_id,
                )
                self._schedule_interrupted_persistence(
                    session_key=session_key,
                    turn_id=active_turn.turn_id,
                    state=interrupt_state,
                )
                cancelled = True
            elif not task.done():
                _ = self._agent_loop.request_interrupt(
                    session_key,
                    sender="desktop",
                    command="/cancel",
                )
                cancelled = True
        coordinator = self._tts_coordinators.pop(normalized_turn_id, None)
        if coordinator is not None:
            coordinator.cancel()
            cancelled = True
        return cancelled

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
        tts = self._create_tts_coordinator(
            request_id=request_id,
            session_key=session_key,
            metadata=metadata,
            emit_event=emit_event,
        )
        reply_announced = False
        tts_received_streamed_content = False

        async def _announce_voice_reply() -> None:
            nonlocal reply_announced
            if tts is None or reply_announced:
                return
            reply_announced = True
            await self._emit_payload(
                emit_event,
                BridgeEvent(
                    id=request_id,
                    type="event",
                    method="voice.reply.started",
                    payload={
                        "session_key": session_key,
                        "request_id": request_id,
                        "voice_turn_id": tts.turn_id,
                        "has_voice": tts.enabled,
                    },
                ).to_dict(),
            )

        async def _on_delta(event: StreamDeltaReady) -> None:
            nonlocal tts_received_streamed_content
            if event.session_key != session_key:
                return
            if tts is not None and event.content_delta:
                await _announce_voice_reply()
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
            if tts is not None and event.content_delta:
                tts_received_streamed_content = True
                tts.push(event.content_delta)

        async def _on_done(event: TurnCommitted) -> None:
            if event.session_key != session_key:
                return
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.done",
                payload={
                    "session_key": event.session_key,
                    "turn_id": turn_id,
                    "role_id": self._role_id_from_session_key(event.session_key),
                    "reply": event.assistant_response,
                    "thinking": event.thinking,
                    "tools_used": list(event.tools_used),
                    "total_tokens": event.total_tokens,
                    "thinking_duration_ms": event.thinking_duration_ms,
                },
            )
            collected.append(bridge_event)
            await self._emit_payload(emit_event, bridge_event.to_dict())
            if (
                tts is not None
                and not tts_received_streamed_content
                and event.assistant_response
            ):
                # Some providers commit a complete reply without emitting text deltas.
                await _announce_voice_reply()
                tts.push(event.assistant_response)

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
        try:
            _ = await self._agent_loop.process_direct(
                content,
                session_key=session_key,
                channel="desktop",
                chat_id=session_key,
                omit_user_turn=omit_user_turn,
                media=media,
                metadata=metadata,
                stream_events=self._streaming_enabled,
            )
            if tts is not None:
                await _announce_voice_reply()
                tts.finish()
                self._track_tts(tts)
            await asyncio.sleep(0)
            session = self._session_manager.get_or_create(session_key)
            role_id = self._role_id_from_session_key(session_key)
            if role_id:
                self._sync_desktop_session_thread(session, role_id=role_id)
            await self._emit_session_updated(
                request_id=request_id,
                session=session,
                emit_event=emit_event,
            )
            return session, collected
        except asyncio.CancelledError:
            if tts is not None:
                await self._terminate_voice_reply(
                    tts,
                    announce=_announce_voice_reply,
                )
            raise
        except Exception as exc:
            if tts is not None:
                await self._terminate_voice_reply(
                    tts,
                    announce=_announce_voice_reply,
                )
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.error",
                payload={
                    "session_key": session_key,
                    "turn_id": turn_id,
                    "message": str(exc),
                },
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
                    emit_event=emit_event,
                )
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("desktop chat turn failed: %s", session_key)

        voice_turn_id = (
            str(metadata.get("voice_turn_id") or "").strip()
            if isinstance(metadata, dict) and metadata.get("input_method") == "voice"
            else ""
        )
        task = asyncio.create_task(_runner(), name=f"desktop-chat:{session_key}")
        self._tasks_by_session[session_key] = _DesktopChatTurn(
            task=task,
            turn_id=turn_id,
            voice_turn_id=voice_turn_id,
        )
        if voice_turn_id:
            self._voice_turn_tasks[voice_turn_id] = (session_key, task)
        task.add_done_callback(
            lambda completed, key=session_key, turn_id=voice_turn_id: self._discard_task(
                key,
                completed,
                turn_id,
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
        for coordinator in self._tts_coordinators.values():
            coordinator.cancel()
        if self._tts_tasks:
            _ = await asyncio.gather(*self._tts_tasks, return_exceptions=True)
        self._tts_coordinators.clear()
        self._voice_turn_tasks.clear()
        self._tts_tasks.clear()

    async def wait_for_tts(self) -> None:
        """Waits for background TTS jobs without waiting for unrelated chat turns."""

        if self._tts_tasks:
            _ = await asyncio.gather(*list(self._tts_tasks))

    def _create_tts_coordinator(
        self,
        *,
        request_id: str,
        session_key: str,
        metadata: dict[str, object] | None,
        emit_event: EventEmitter,
    ) -> TtsTurnCoordinator | None:
        if self._tts_service is None or not isinstance(metadata, dict):
            return None
        if metadata.get("input_method") != "voice":
            return None
        turn_id = str(metadata.get("voice_turn_id") or "").strip()
        if not turn_id:
            return None
        session = self._session_manager.get_or_create(session_key)
        session_metadata = getattr(session, "metadata", {})
        runtime_config = (
            session_metadata.get("role_runtime_config")
            if isinstance(session_metadata, dict)
            else {}
        )
        mood = (
            session_metadata.get("current_mood")
            if isinstance(session_metadata, dict)
            else ""
        )

        async def _emit(payload: dict[str, Any]) -> None:
            await self._emit_payload(emit_event, payload)

        coordinator = TtsTurnCoordinator(
            voice_service=self._tts_service,
            session_key=session_key,
            request_id=request_id,
            turn_id=turn_id,
            settings=resolve_role_tts_settings(runtime_config, mood),
            emit_event=_emit,
        )
        self._tts_coordinators[turn_id] = coordinator
        return coordinator

    def _track_tts(self, coordinator: TtsTurnCoordinator) -> None:
        task = asyncio.create_task(
            coordinator.wait(), name=f"desktop-tts-wait:{id(coordinator)}"
        )
        self._tts_tasks.add(task)

        def _discard(completed: asyncio.Task[None]) -> None:
            self._tts_tasks.discard(completed)
            self._discard_tts_coordinator(coordinator)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.error(
                    "desktop TTS task failed turn=%s",
                    coordinator.turn_id,
                    exc_info=error,
                )

        task.add_done_callback(_discard)

    def _discard_tts_coordinator(self, coordinator: TtsTurnCoordinator) -> None:
        if self._tts_coordinators.get(coordinator.turn_id) is coordinator:
            _ = self._tts_coordinators.pop(coordinator.turn_id, None)

    async def _terminate_voice_reply(
        self,
        coordinator: TtsTurnCoordinator,
        *,
        announce: Callable[[], Awaitable[None]],
    ) -> None:
        """Closes a voice lifecycle when the chat worker exits abnormally."""

        await announce()
        await coordinator.terminate()
        self._discard_tts_coordinator(coordinator)

    def _discard_task(
        self,
        session_key: str,
        task: asyncio.Task[None],
        voice_turn_id: str,
    ) -> None:
        active_turn = self._tasks_by_session.get(session_key)
        if active_turn is not None and active_turn.task is task:
            _ = self._tasks_by_session.pop(session_key, None)
        if voice_turn_id and self._voice_turn_tasks.get(voice_turn_id) == (
            session_key,
            task,
        ):
            _ = self._voice_turn_tasks.pop(voice_turn_id, None)
