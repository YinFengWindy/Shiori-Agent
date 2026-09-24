from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from core.roles import RoleAggregateService
from infra.channels.reply_context import build_inbound_text_with_reply_context

from .app_service import DesktopAppService
from .chat_service import ChatTurnBusyError, DesktopChatService
from .session_presenter import DesktopSessionPresenter

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]

# Metadata that belongs to the original spoken input and must not re-arm voice
# playback or ASR bookkeeping when the turn is retried.
_VOICE_METADATA_KEYS = frozenset(
    {
        "input_method",
        "voice_turn_id",
        "asr_metrics",
        "asr_provider",
        "asr_request_id",
        "asr_duration_ms",
        "audio_duration_ms",
    }
)


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
            result = await self._chat_service.cancel_chat_turn_async(
                str(payload.get("session_key") or "").strip(),
                str(payload.get("turn_id") or "").strip(),
            )
            response: dict[str, Any] = {
                "status": result.status,
                "message": result.message,
                "session_key": result.session_key,
                "turn_id": result.turn_id,
            }
            if result.session is not None and result.interrupted_message is not None:
                response["session"] = self._session_presenter.serialize_summary(
                    result.session
                )
                response["message_payload"] = self._session_presenter.serialize_message(
                    result.interrupted_message
                )
            return response
        if method == "chat.retry":
            return await self._retry(
                payload, request_id=request_id, emit_event=emit_event
            )
        return None

    async def _retry(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any]:
        """Re-runs the latest failed turn on its already persisted user message.

        A failed desktop turn persists the user message and nothing after it
        (errors are never stored), so the retryable turn is exactly "the
        session ends with this user message". Anything else — a reply already
        followed, or another message arrived — is refused, and the single
        timeline is never rewritten or given a duplicate user message.
        """
        role_id = str(payload.get("role_id") or "").strip()
        turn_id = str(payload.get("turn_id") or "").strip()
        user_message_id = str(payload.get("user_message_id") or "").strip()
        if not turn_id:
            raise ValueError("turn_id 不能为空")
        if not user_message_id:
            raise ValueError("user_message_id 不能为空")
        aggregate = await self._role_service.open_role_async(role_id)
        session = aggregate.session
        if self._chat_service.is_busy(session.key):
            raise ChatTurnBusyError("当前会话已有正在执行的聊天任务")
        user_message = session.messages[-1] if session.messages else None
        if (
            user_message is None
            or user_message.get("role") != "user"
            or str(user_message.get("id") or "") != user_message_id
        ):
            raise ValueError("只能重试最近一次失败的回合")

        content = str(user_message.get("content") or "")
        raw_metadata = user_message.get("metadata")
        stored_metadata = (
            cast(dict[str, object], raw_metadata)
            if isinstance(raw_metadata, dict)
            else {}
        )
        raw_media = user_message.get("media")
        media = (
            [str(item) for item in cast(list[object], raw_media)]
            if isinstance(raw_media, list)
            else []
        )
        metadata: dict[str, object] = {
            key: value
            for key, value in stored_metadata.items()
            # A retry is typed, not spoken: the original voice turn is over.
            if key not in _VOICE_METADATA_KEYS
        }
        metadata.update(
            {"request_id": request_id, "delivery_key": request_id, "turn_id": turn_id}
        )
        reply_to_content = str(metadata.get("reply_to_content") or "").strip()
        inbound_content = (
            build_inbound_text_with_reply_context(
                user_text=content,
                reply_text=reply_to_content,
                reply_sender=str(metadata.get("reply_to_sender") or "").strip(),
            )
            if reply_to_content
            else content
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
            "session": self._session_presenter.serialize_summary(session),
            "message": self._session_presenter.serialize_message(user_message),
            "turn_id": turn_id,
            "events": [],
        }

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
        persisted_message = await self._app_service.persist_desktop_user_message(
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
            "session": self._session_presenter.serialize_summary(session),
            "message": self._session_presenter.serialize_message(persisted_message),
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
