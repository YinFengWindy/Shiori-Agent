from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.roles import RoleAggregateService
from infra.channels.reply_context import build_inbound_text_with_reply_context

from .app_service import DesktopAppService
from .chat_service import ChatTurnBusyError, DesktopChatService
from .session_presenter import DesktopSessionPresenter

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]


class DesktopChatRequestHandler:
    """Owns desktop chat request normalization and turn dispatch."""

    def __init__(
        self,
        *,
        role_service: RoleAggregateService,
        app_service: DesktopAppService,
        chat_service: DesktopChatService,
        start_chat_turn: Callable[..., None],
        session_presenter: DesktopSessionPresenter,
        sanitize_voice_metrics: Callable[[object], dict[str, str | int] | None],
    ) -> None:
        self._role_service = role_service
        self._app_service = app_service
        self._chat_service = chat_service
        self._start_chat_turn = start_chat_turn
        self._session_presenter = session_presenter
        self._sanitize_voice_metrics = sanitize_voice_metrics

    async def handle(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any] | None:
        if method == "chat.send":
            return await self._send(
                payload, request_id=request_id, emit_event=emit_event
            )
        if method == "chat.cancel":
            result = self._chat_service.cancel_chat_turn(
                str(payload.get("session_key") or "").strip(),
                str(payload.get("turn_id") or "").strip(),
            )
            return {
                "status": result.status,
                "message": result.message,
                "session_key": result.session_key,
                "turn_id": result.turn_id,
            }
        return None

    async def _send(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any]:
        role_id = str(payload.get("role_id") or "").strip()
        turn_id = str(
            payload.get("turn_id") or payload.get("client_message_id") or request_id
        ).strip()
        content = str(payload.get("content") or "").strip()
        raw_media = payload.get("media")
        media = (
            [str(item).strip() for item in raw_media if str(item).strip()]
            if isinstance(raw_media, list)
            else []
        )
        if not content and not media:
            raise ValueError("content 和 media 不能同时为空")
        if not turn_id:
            raise ValueError("turn_id 不能为空")
        aggregate = await self._role_service.open_role_async(role_id)
        session = aggregate.session
        if self._chat_service.is_busy(session.key):
            raise ChatTurnBusyError("当前会话已有正在执行的聊天任务")

        reply_to_content = str(payload.get("reply_to_content") or "").strip()
        reply_to_sender = str(payload.get("reply_to_sender") or "").strip()
        inbound_content = content
        metadata = self._build_metadata(payload, request_id=request_id)
        if reply_to_content:
            metadata["reply_to_content"] = reply_to_content
            metadata["persisted_user_content"] = content
            inbound_content = build_inbound_text_with_reply_context(
                user_text=content,
                reply_text=reply_to_content,
                reply_sender=reply_to_sender,
            )
        metadata = self._app_service.build_desktop_user_message_metadata(
            metadata,
            role_id=aggregate.role.id,
            chat_id=session.key,
        )
        await self._app_service.persist_desktop_user_message(
            session=session,
            role_id=aggregate.role.id,
            content=content,
            media=media,
            metadata=metadata,
        )
        self._start_chat_turn(
            request_id=request_id,
            turn_id=turn_id,
            session_key=session.key,
            content=inbound_content,
            media=media,
            metadata=metadata,
            omit_user_turn=True,
            emit_event=emit_event,
        )
        return {
            "session": self._session_presenter.serialize(session),
            "turn_id": turn_id,
            "events": [],
        }

    def _build_metadata(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "request_id": request_id,
            "delivery_key": request_id,
        }
        client_message_id = str(payload.get("client_message_id") or "").strip()
        if client_message_id:
            metadata["client_message_id"] = client_message_id
        turn_id = str(payload.get("turn_id") or client_message_id or request_id).strip()
        if turn_id:
            metadata["turn_id"] = turn_id
        if str(payload.get("input_method") or "").strip() == "voice":
            metadata["input_method"] = "voice"
            voice_turn_id = str(payload.get("voice_turn_id") or "").strip()
            if voice_turn_id:
                metadata["voice_turn_id"] = voice_turn_id
            asr_metrics = self._sanitize_voice_metrics(payload.get("asr_metrics"))
            if asr_metrics is not None:
                metadata["asr_metrics"] = asr_metrics
            for key in ("asr_provider", "asr_request_id"):
                value = str(payload.get(key) or "").strip()
                if value:
                    metadata[key] = value
            for key in ("asr_duration_ms", "audio_duration_ms"):
                value = payload.get(key)
                if isinstance(value, (int, float)) and value >= 0:
                    metadata[key] = value
        reply_to_message_id = str(payload.get("reply_to_message_id") or "").strip()
        if reply_to_message_id:
            metadata["reply_to_message_id"] = reply_to_message_id
        reply_to_sender = str(payload.get("reply_to_sender") or "").strip()
        if reply_to_sender:
            metadata["reply_to_sender"] = reply_to_sender
        return metadata
