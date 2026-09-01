from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .image_service import DesktopImageService
from .session_presenter import DesktopSessionPresenter

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]
EmitSessionUpdated = Callable[..., Awaitable[None]]


class DesktopImageRequestHandler:
    """Handles NovelAI bridge requests while preserving session update events."""

    def __init__(
        self,
        *,
        image_service: DesktopImageService,
        session_presenter: DesktopSessionPresenter,
        emit_session_updated: EmitSessionUpdated,
    ) -> None:
        self._image_service = image_service
        self._session_presenter = session_presenter
        self._emit_session_updated = emit_session_updated

    async def handle(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any] | None:
        if method == "novelai.generate":
            return {"result": await self._image_service.generate(payload)}
        if method == "novelai.regenerateMessageMedia":
            result, session = await self._image_service.regenerate_message_media(
                payload
            )
            await self._emit_session_updated(
                request_id=request_id,
                session=session,
                emit_event=emit_event,
                message_id=str(payload.get("message_id") or "").strip(),
                change="message_updated",
            )
            return {
                "result": result,
                "session": self._session_presenter.serialize_summary(session),
                "message": self._session_presenter.serialize_message(
                    next(
                        message
                        for message in session.messages
                        if str(message.get("id") or "")
                        == str(payload.get("message_id") or "").strip()
                    )
                ),
            }
        if method == "novelai.history":
            return {"records": self._image_service.history(payload)}
        if method == "novelai.prompt_tags.list":
            return {"entries": self._image_service.prompt_tags_list()}
        if method == "novelai.prompt_tags.upsert":
            return {"entry": self._image_service.prompt_tags_upsert(payload)}
        if method == "novelai.prompt_tags.delete":
            self._image_service.prompt_tags_delete(payload)
            return {}
        return None
