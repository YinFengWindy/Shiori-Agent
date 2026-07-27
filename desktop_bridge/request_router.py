from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agent.screen_observation.service import ScreenObservationService

from .chat_requests import DesktopChatRequestHandler
from .image_requests import DesktopImageRequestHandler
from .role_requests import DesktopRoleRequestHandler
from .session_task_requests import DesktopSessionTaskRequestHandler
from .voice_handler import DesktopVoiceHandler
from .world_simulation_handler import WorldSimulationHandler

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]


class DesktopBridgeRequestRouter:
    """Routes bridge RPCs to one domain handler without owning bridge lifecycle."""

    def __init__(
        self,
        *,
        roles: DesktopRoleRequestHandler,
        sessions_and_tasks: DesktopSessionTaskRequestHandler,
        chat: DesktopChatRequestHandler,
        images: DesktopImageRequestHandler,
        voice: DesktopVoiceHandler,
        worlds: WorldSimulationHandler,
        observation: ScreenObservationService | None,
    ) -> None:
        self._roles = roles
        self._sessions_and_tasks = sessions_and_tasks
        self._chat = chat
        self._images = images
        self._voice = voice
        self._worlds = worlds
        self._observation = observation

    async def dispatch(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any] | None:
        if method in {"observation.analyze", "observation.remember"}:
            if self._observation is None:
                raise RuntimeError("desktop observation service unavailable")
            if method == "observation.analyze":
                return await self._observation.analyze(payload)
            return await self._observation.remember(payload)
        world_result = self._worlds.handle(method, payload, request_id=request_id)
        if world_result is not None:
            return world_result
        if method == "health":
            return {"ok": True}
        voice_result = await self._voice.handle(method, payload)
        if voice_result is not None:
            return voice_result
        result = await self._roles.handle(method, payload)
        if result is not None:
            return result
        for handler in (self._sessions_and_tasks, self._chat, self._images):
            result = await handler.handle(
                method,
                payload,
                request_id=request_id,
                emit_event=emit_event,
            )
            if result is not None:
                return result
        return None
