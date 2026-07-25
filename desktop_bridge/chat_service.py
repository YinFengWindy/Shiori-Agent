from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady, TurnCommitted
from desktop_bridge.models import BridgeEvent
from desktop_bridge.tts_coordinator import TtsTurnCoordinator, resolve_role_tts_settings
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
        self._tts_tasks: set[asyncio.Task[None]] = set()
        self._tts_coordinators: set[TtsTurnCoordinator] = set()

    def is_busy(self, session_key: str) -> bool:
        """Returns whether the session already has an active desktop turn."""

        task = self._tasks_by_session.get(session_key)
        return task is not None and not task.done()

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

        async def _on_delta(event: StreamDeltaReady) -> None:
            nonlocal reply_announced
            if event.session_key != session_key:
                return
            if tts is not None and not reply_announced and event.content_delta:
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
                            "has_voice": tts.enabled,
                        },
                    ).to_dict(),
                )
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
            if tts is not None:
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
                if not reply_announced:
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
                                "has_voice": tts.enabled,
                            },
                        ).to_dict(),
                    )
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
        task.add_done_callback(
            lambda completed, key=session_key: self._discard_task(key, completed)
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
        for coordinator in self._tts_coordinators:
            coordinator.cancel()
        if self._tts_tasks:
            _ = await asyncio.gather(*self._tts_tasks, return_exceptions=True)
        self._tts_coordinators.clear()
        self._tts_tasks.clear()

    async def wait_for_tts(self) -> None:
        """Waits for background TTS jobs without waiting for unrelated chat turns."""

        if self._tts_tasks:
            _ = await asyncio.gather(*list(self._tts_tasks), return_exceptions=True)

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
        session = self._session_manager.get_or_create(session_key)
        session_metadata = getattr(session, "metadata", {})
        runtime_config = session_metadata.get("role_runtime_config") if isinstance(session_metadata, dict) else {}
        mood = session_metadata.get("current_mood") if isinstance(session_metadata, dict) else ""

        async def _emit(payload: dict[str, Any]) -> None:
            await self._emit_payload(emit_event, payload)

        return TtsTurnCoordinator(
            voice_service=self._tts_service,
            session_key=session_key,
            request_id=request_id,
            settings=resolve_role_tts_settings(runtime_config, mood),
            emit_event=_emit,
        )

    def _track_tts(self, coordinator: TtsTurnCoordinator) -> None:
        if not coordinator.enabled:
            return
        self._tts_coordinators.add(coordinator)
        task = asyncio.create_task(coordinator.wait(), name=f"desktop-tts-wait:{id(coordinator)}")
        self._tts_tasks.add(task)

        def _discard(completed: asyncio.Task[None]) -> None:
            self._tts_tasks.discard(completed)
            self._tts_coordinators.discard(coordinator)

        task.add_done_callback(_discard)

    def _discard_task(self, session_key: str, task: asyncio.Task[None]) -> None:
        if self._tasks_by_session.get(session_key) is task:
            _ = self._tasks_by_session.pop(session_key, None)
