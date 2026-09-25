"""Shared QQ stream identity, update, and safe replacement rules."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .formatting import http_status_code

# Session and target scope the originating transport message's stream ownership.
_LiveTurnKey = tuple[str, str, str]

logger = logging.getLogger(__name__)


def _definitely_rejected(error: Exception) -> bool:
    # Timeout/server errors do not establish whether QQ accepted the write.
    status = http_status_code(error)
    return status is not None and 400 <= status < 500 and status != 408


@dataclass
class _StreamState:
    openid: str
    msg_id: str
    msg_seq: int
    stream_msg_id: str = ""
    index: int = 0
    completed: bool = False
    error: Exception | None = None


class _StreamDeliveryMixin:
    """Keeps both live replies and tool pushes on one acknowledged message."""

    async def _update_stream(
        self, state: _StreamState, text: str, *, terminal: bool
    ) -> str:
        cancellation = None
        try:
            token = await self._get_access_token()
            body: dict[str, Any] = {
                "input_mode": "replace",
                "input_state": 10 if terminal else 1,
                "content_type": "markdown",
                "content_raw": text,
                "event_id": state.msg_id,
                "msg_id": state.msg_id,
                "msg_seq": state.msg_seq,
                "index": state.index,
            }
            if state.stream_msg_id:
                body["stream_msg_id"] = state.stream_msg_id
            request = asyncio.create_task(
                self._api_request(
                    "POST", f"/v2/users/{state.openid}/stream_messages", body, token
                )
            )
            try:
                result = await asyncio.shield(request)
            except asyncio.CancelledError as exc:
                # Once QQ may have accepted the write, preserve its receipt
                # before propagating cancellation to the delivery boundary.
                cancellation = exc
                result = await request
            message_id = str(result.get("id") or state.stream_msg_id).strip()
            if not message_id:
                raise RuntimeError("QQBot 流式响应缺少消息 ID，发送结果不确定")
        except Exception as exc:
            state.error = exc
            if cancellation is not None:
                logger.exception("[qqbot] 取消流式投递后等待发送回执失败")
                raise cancellation from exc
            raise
        state.stream_msg_id = message_id
        state.index += 1
        state.completed = terminal
        state.error = None
        if cancellation is not None:
            raise cancellation
        return message_id

    async def _prepare_stream_fallback(self, state: _StreamState) -> None:
        # A replacement is safe only after a definite rejection and confirmed
        # removal of any acknowledged preview. Never hide a failed recall.
        if state.error is not None and not _definitely_rejected(state.error):
            raise state.error
        if state.stream_msg_id:
            await self._delete_message(state.openid, state.stream_msg_id)

    async def _finish_stream(self, state: _StreamState, text: str) -> str:
        """Terminates the same message, or clears it before a safe replacement."""
        if state.error is not None:
            if not _definitely_rejected(state.error):
                raise state.error
            if not state.stream_msg_id:
                return ""
        try:
            return await self._update_stream(state, text, terminal=True)
        except Exception:
            await self._prepare_stream_fallback(state)
            return ""
