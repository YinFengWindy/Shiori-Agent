from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


from .chat_requests import DesktopChatRequestHandler
from .account_requests import DesktopAccountRequestHandler
from .model_connection_probe import probe_model_connection
from .plugin_requests import DesktopPluginRequestHandler
from .role_requests import DesktopRoleRequestHandler
from .session_task_requests import DesktopSessionTaskRequestHandler
from .voice.voice_handler import DesktopVoiceHandler

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]


class DesktopBridgeRequestRouter:
    """Routes bridge RPCs to one domain handler without owning bridge lifecycle."""

    def __init__(
        self,
        *,
        roles: DesktopRoleRequestHandler,
        sessions_and_tasks: DesktopSessionTaskRequestHandler,
        chat: DesktopChatRequestHandler,
        voice: DesktopVoiceHandler,
        plugins: DesktopPluginRequestHandler,
        accounts: DesktopAccountRequestHandler | None = None,
    ) -> None:
        self._roles = roles
        self._sessions_and_tasks = sessions_and_tasks
        self._chat = chat
        self._voice = voice
        self._plugins = plugins
        self._accounts = accounts

    async def dispatch(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any] | None:
        if method == "health":
            return {"ok": True}
        if method == "models.test":
            # Stateless: probes the unsaved draft without touching runtime state.
            return await probe_model_connection(payload)
        plugin_result = await self._plugins.handle(method, payload)
        if plugin_result is not None:
            return plugin_result
        if self._accounts is not None:
            account_result = await self._accounts.handle(method, payload)
            if account_result is not None:
                return account_result
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
