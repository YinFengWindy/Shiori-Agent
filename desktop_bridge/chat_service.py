from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady, TurnCommitted
from desktop_bridge.models import BridgeEvent
from desktop_bridge.role_tts_settings import resolve_role_tts_settings
from desktop_bridge.tts_coordinator import TtsTurnCoordinator
from desktop_bridge.voice_service import VoiceService
from session.manager import Session, SessionManager

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
    ) -> None:
        self._agent_loop = agent_loop
        self._event_bus = event_bus
        self._session_manager = session_manager
        self._role_id_from_session_key = role_id_from_session_key
        self._sync_desktop_session_thread = sync_desktop_session_thread
        self._emit_payload = emit_payload
        self._emit_session_updated = emit_session_updated
        self._tts_service = tts_service
        self._tasks_by_session: dict[str, asyncio.Task[None]] = {}
        self._voice_turn_tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}
        self._tts_tasks: set[asyncio.Task[None]] = set()
        self._tts_coordinators: dict[str, TtsTurnCoordinator] = {}

    def is_busy(self, session_key: str) -> bool:
        """Returns whether the session already has an active desktop turn."""

        task = self._tasks_by_session.get(session_key)
        return task is not None and not task.done()

    def cancel_voice_turn(self, turn_id: str) -> bool:
        """Cancels chat and synthesis work owned by one voice input turn."""

        normalized_turn_id = turn_id.strip()
        if not normalized_turn_id:
            return False
        cancelled = False
        coordinator = self._tts_coordinators.pop(normalized_turn_id, None)
        if coordinator is not None:
            coordinator.cancel()
            cancelled = True
        owner = self._voice_turn_tasks.get(normalized_turn_id)
        if owner is not None:
            session_key, task = owner
            if not task.done():
                _ = self._agent_loop.request_interrupt(
                    session_key,
                    sender="desktop",
                    command="/cancel",
                )
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
    ) -> tuple[Session, list[BridgeEvent]]:
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
                    "role_id": self._role_id_from_session_key(event.session_key),
                    "reply": event.assistant_response,
                    "thinking": event.thinking,
                    "tools_used": list(event.tools_used),
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

        self._event_bus.on(StreamDeltaReady, _on_delta)
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
                stream_events=True,
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
        except Exception as exc:
            if tts is not None:
                tts.cancel()
                self._discard_tts_coordinator(tts)
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.error",
                payload={
                    "session_key": session_key,
                    "message": str(exc),
                },
            )
            collected.append(bridge_event)
            await self._emit_payload(emit_event, bridge_event.to_dict())
            raise
        finally:
            self._event_bus.off(StreamDeltaReady, _on_delta)
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
    ) -> None:
        if self.is_busy(session_key):
            raise ChatTurnBusyError(f"会话 {session_key} 已有正在执行的聊天任务")

        async def _runner() -> None:
            try:
                _ = await self.run_chat_turn(
                    request_id=request_id,
                    session_key=session_key,
                    content=content,
                    media=media,
                    metadata=metadata,
                    omit_user_turn=omit_user_turn,
                    emit_event=emit_event,
                )
            except Exception:
                logger.exception("desktop chat turn failed: %s", session_key)

        task = asyncio.create_task(_runner(), name=f"desktop-chat:{session_key}")
        self._tasks_by_session[session_key] = task
        voice_turn_id = (
            str(metadata.get("voice_turn_id") or "").strip()
            if isinstance(metadata, dict) and metadata.get("input_method") == "voice"
            else ""
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

        tasks = list(self._tasks_by_session.values())
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
        if not bool(getattr(self._tts_service, "tts_enabled", True)):
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
        if not coordinator.enabled:
            self._discard_tts_coordinator(coordinator)
            return
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

    def _discard_task(
        self,
        session_key: str,
        task: asyncio.Task[None],
        voice_turn_id: str,
    ) -> None:
        if self._tasks_by_session.get(session_key) is task:
            _ = self._tasks_by_session.pop(session_key, None)
        if voice_turn_id and self._voice_turn_tasks.get(voice_turn_id) == (
            session_key,
            task,
        ):
            _ = self._voice_turn_tasks.pop(voice_turn_id, None)
