from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from agent.screen_observation.service import ScreenObservationService

if TYPE_CHECKING:
    from agent.plugins.manager import PluginManager

from .chat_requests import DesktopChatRequestHandler
from .image_requests import DesktopImageRequestHandler
from .role_requests import DesktopRoleRequestHandler
from .session_task_requests import DesktopSessionTaskRequestHandler
from .voice_handler import DesktopVoiceHandler
from .story_simulation_handler import StorySimulationHandler

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
        stories: StorySimulationHandler,
        observation: ScreenObservationService | None,
        plugin_manager: "PluginManager | None" = None,
    ) -> None:
        self._roles = roles
        self._sessions_and_tasks = sessions_and_tasks
        self._chat = chat
        self._images = images
        self._voice = voice
        self._stories = stories
        self._observation = observation
        self._plugin_manager = plugin_manager
        self._plugin_handlers = {"novelai": images}

    async def dispatch(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any] | None:
        if method == "plugins.list":
            return {
                "plugins": (
                    self._plugin_manager.public_manifests()
                    if self._plugin_manager is not None
                    else []
                )
            }
        plugin_prefix, separator, _ = method.partition(".")
        plugin_handler = self._plugin_handlers.get(plugin_prefix) if separator else None
        if plugin_handler is not None:
            if self._plugin_manager is not None:
                self._plugin_manager.authorize_rpc(
                    method,
                    known_prefixes=set(self._plugin_handlers),
                )
            return await plugin_handler.handle(
                method,
                payload,
                request_id=request_id,
                emit_event=emit_event,
            )
        if method in {"observation.analyze", "observation.remember"}:
            if self._observation is None:
                raise RuntimeError("desktop observation service unavailable")
            if method == "observation.analyze":
                return await self._observation.analyze(payload)
            return await self._observation.remember(payload)
        story_result = await self._stories.handle(
            method,
            payload,
            request_id=request_id,
            emit_event=emit_event,
        )
        if story_result is not None:
            return story_result
        if method == "health":
            return {"ok": True}
        voice_result = await self._voice.handle(method, payload)
        if voice_result is not None:
            return voice_result
        result = await self._roles.handle(method, payload)
        if result is not None:
            return result
        for handler in (self._sessions_and_tasks, self._chat):
            result = await handler.handle(
                method,
                payload,
                request_id=request_id,
                emit_event=emit_event,
            )
            if result is not None:
                return result
        return None
