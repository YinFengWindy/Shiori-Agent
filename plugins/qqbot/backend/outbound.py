from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import Any

from bus.events import OutboundMessage
from bus.errors import NonRetryableDeliveryError
from core.common.media import detect_image_mime_from_header
from infra.channels.session_key import resolve_outbound_session_key

from .formatting import CHANNEL, SUPPORTED_IMAGE_MIME_TYPES, iter_stream_chunks
from .stream_delivery import _StreamState

logger = logging.getLogger(__name__)


class _OutboundMixin:
    """Owns QQBot C2C text, image, stream, and delivery-status output."""

    async def _on_response(self, msg: OutboundMessage) -> None:
        turn_key = (
            resolve_outbound_session_key(msg, default_channel=CHANNEL),
            msg.chat_id,
            str(msg.metadata.get("external_message_id") or ""),
        )
        first_id: str | None = None
        try:
            await self._finish_live_tasks(turn_key)
            if turn_key in self._live_states:
                if msg.content.strip():
                    first_id = await self._finish_stream(
                        self._live_states[turn_key], msg.content
                    )
                else:
                    # An unfinished preview next to the fallback message would
                    # show the reply twice, so withdraw it first.
                    await self._prepare_stream_fallback(self._live_states[turn_key])
            if msg.content.strip() and not first_id:
                first_id = await self.send(msg.chat_id, msg.content)
            for image in msg.media:
                image_id = await self.send_image(msg.chat_id, image)
                first_id = first_id or image_id
        except asyncio.CancelledError:
            self._record_delivery_status(msg, "failed", first_id)
            await self._cleanup_cancelled_stream(self._live_states.get(turn_key))
            raise
        except Exception as exc:
            self._record_delivery_status(msg, "failed", first_id)
            # This boundary has already exhausted safe stream recovery. A bus
            # replay can duplicate a preview, a fallback, or an earlier image.
            raise NonRetryableDeliveryError(
                f"QQBot 投递失败，禁止自动重发：{exc}"
            ) from exc
        else:
            self._record_delivery_status(msg, "sent", first_id)
        finally:
            self._clear_live_turn(turn_key)

    def _record_delivery_status(
        self, msg: OutboundMessage, status: str, external_message_id: str | None = None
    ) -> None:
        if self._channel_hub is None:
            return
        self._channel_hub.mark_delivery(
            msg,
            default_channel=CHANNEL,
            delivery_status=status,
            external_message_id=external_message_id or "",
        )

    async def send_proactive(self, chat_id: str, message: str) -> str | None:
        """Sends a proactive C2C text message; returns the platform message id."""
        return await self.send(chat_id, message)

    async def send(self, chat_id: str, message: str) -> str | None:
        """Sends a Markdown message to a C2C target; returns its message id."""
        kind, target = self._parse_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("当前 QQBotChannel 仅支持私聊 c2c")
        token = await self._get_access_token()
        sent = await self._api_request(
            "POST",
            f"/v2/users/{target}/messages",
            self._build_message_body(message),
            token,
        )
        return _response_message_id(sent)

    async def send_image(self, chat_id: str, image: str) -> str | None:
        """Uploads and sends a PNG, JPEG, WebP, or GIF to C2C; returns its id."""
        kind, target = self._parse_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("当前 QQBotChannel 仅支持私聊 c2c")
        upload_body = self._build_image_upload_body(image)
        token = await self._get_access_token()
        upload = await self._api_request(
            "POST", f"/v2/users/{target}/files", upload_body, token
        )
        file_info = str(upload.get("file_info") or "").strip()
        if not file_info:
            raise RuntimeError("QQBot 图片上传响应缺少 file_info")
        sent = await self._api_request(
            "POST",
            f"/v2/users/{target}/messages",
            {
                "msg_type": 7,
                "media": {"file_info": file_info},
                "msg_seq": self._next_msg_seq(),
            },
            token,
        )
        return _response_message_id(sent)

    @staticmethod
    def _build_image_upload_body(image: str) -> dict[str, Any]:
        source = str(image or "").strip()
        if not source:
            raise ValueError("QQBot 图片来源不能为空")
        if source.startswith(("http://", "https://")):
            return {"file_type": 1, "url": source, "srv_send_msg": False}
        path = Path(source).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"QQBot 图片文件不存在: {path}")
        raw = path.read_bytes()
        mime = detect_image_mime_from_header(raw[:4096])
        if mime not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ValueError("QQBot 图片仅支持 PNG、JPEG、WebP 和 GIF")
        return {
            "file_type": 1,
            "file_data": base64.b64encode(raw).decode("ascii"),
            "srv_send_msg": False,
        }

    async def send_stream(self, chat_id: str, message: str) -> str | None:
        """Sends a complete proactive response using the official stream API.

        Returns the platform id of whichever message actually carried it: the
        stream message, or the plain message used as fallback.
        """
        kind, target = self._parse_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("当前 QQBotChannel 仅支持私聊 c2c")
        msg_id = self._last_c2c_msg_id.get(target)
        if not msg_id:
            return await self.send(chat_id, message)
        stream_id = await self._send_stream_c2c(target, msg_id, message)
        return stream_id or await self.send(chat_id, message)

    async def _send_stream_c2c(self, openid: str, msg_id: str, message: str) -> str:
        state = _StreamState(openid=openid, msg_id=msg_id, msg_seq=self._next_msg_seq())
        chunks = iter_stream_chunks(message)
        try:
            try:
                for content in chunks[:-1]:
                    await self._update_stream(state, content, terminal=False)
            except Exception:
                # A rejected continuation may still accept an in-place terminal
                # update. Live replies and pushes share the same recovery.
                return await self._finish_stream(state, message)
            return await self._finish_stream(state, message)
        except asyncio.CancelledError:
            await self._cleanup_cancelled_stream(state)
            raise

    async def _send_input_notify(self, openid: str, msg_id: str) -> None:
        try:
            token = await self._get_access_token()
            await self._api_request(
                "POST",
                f"/v2/users/{openid}/messages",
                {
                    "msg_type": 6,
                    "input_notify": {"input_type": 1, "input_second": 60},
                    "msg_seq": self._next_msg_seq(),
                    "msg_id": msg_id,
                },
                token,
            )
        except Exception as exc:
            logger.debug("[qqbot] 发送输入中提示失败: %s", exc)

    async def _delete_message(self, openid: str, message_id: str) -> None:
        token = await self._get_access_token()
        await self._api_request(
            "DELETE",
            f"/v2/users/{openid}/messages/{message_id}",
            token=token,
        )

    def _build_message_body(self, message: str) -> dict[str, Any]:
        return {
            "markdown": {"content": message},
            "msg_type": 2,
            "msg_seq": self._next_msg_seq(),
        }

    @staticmethod
    def _next_msg_seq() -> int:
        return int(time.time() * 1000) % 65536

    @staticmethod
    def _parse_chat_id(chat_id: str) -> tuple[str, str]:
        value = chat_id.strip()
        if value.startswith("qqbot:"):
            value = value[len("qqbot:") :]
        if ":" not in value:
            return "c2c", value
        kind, target = value.split(":", 1)
        if kind not in {"c2c", "group"} or not target:
            raise ValueError(f"无效的 QQBot chat_id: {chat_id!r}")
        return kind, target


def _response_message_id(response: dict[str, Any]) -> str | None:
    """Reads the message id the QQBot send API returns; None when absent."""
    message_id = response.get("id")
    return str(message_id) if message_id else None
