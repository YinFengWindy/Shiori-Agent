from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady, TurnCommitted
from desktop_bridge.models import BridgeEvent
from session.manager import Session, SessionManager

logger = logging.getLogger("desktop.bridge.chat")


class DesktopChatService:
    """Runs desktop chat turns and bridges lifecycle events back to the bridge stream."""

    def __init__(
        self,
        *,
        agent_loop: AgentLoop,
        event_bus: EventBus,
        session_manager: SessionManager,
        role_id_from_session_key: Callable[[str], str],
        sync_desktop_session_thread: Callable[[Session, str], None],
        emit_payload: Callable[
            [Callable[[dict[str, Any]], Awaitable[None] | None], dict[str, Any]],
            Awaitable[None],
        ],
        emit_session_updated: Callable[
            [str, Session, Callable[[dict[str, Any]], Awaitable[None] | None]],
            Awaitable[None],
        ],
    ) -> None:
        self._agent_loop = agent_loop
        self._event_bus = event_bus
        self._session_manager = session_manager
        self._role_id_from_session_key = role_id_from_session_key
        self._sync_desktop_session_thread = sync_desktop_session_thread
        self._emit_payload = emit_payload
        self._emit_session_updated = emit_session_updated
        self._tasks: set[asyncio.Task[None]] = set()

    async def run_chat_turn(
        self,
        *,
        request_id: str,
        session_key: str,
        content: str,
        media: list[str],
        metadata: dict[str, object] | None,
        omit_user_turn: bool,
        emit_event,
    ) -> tuple[Session, list[BridgeEvent]]:
        collected: list[BridgeEvent] = []

        async def _on_delta(event: StreamDeltaReady) -> None:
            if event.session_key != session_key:
                return
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

        async def _on_done(event: TurnCommitted) -> None:
            if event.session_key != session_key:
                return
            bridge_event = BridgeEvent(
                id=request_id,
                type="event",
                method="chat.done",
                payload={
                    "session_key": event.session_key,
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
            await self._agent_loop.process_direct(
                content,
                session_key=session_key,
                channel="desktop",
                chat_id=session_key,
                omit_user_turn=omit_user_turn,
                media=media,
                metadata=metadata,
                stream_events=True,
            )
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
        emit_event,
    ) -> None:
        async def _runner() -> None:
            try:
                await self.run_chat_turn(
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
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
