from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Any

from bus.events import OutboundMessage
from core.common.media import detect_image_mime_from_header
from infra.channels.session_key import resolve_outbound_session_key

from .formatting import CHANNEL, SUPPORTED_IMAGE_MIME_TYPES, iter_stream_chunks

logger = logging.getLogger(__name__)


class _OutboundMixin:
    """Owns QQBot C2C text, image, stream, and delivery-status output."""

    async def _on_response(self, msg: OutboundMessage) -> None:
        session_key = resolve_outbound_session_key(msg, default_channel=CHANNEL)
        sent_as_stream = False
        send_failed = False
        try:
            if session_key in self._live_states:
                await self._cancel_live_tasks(session_key)
                if msg.content.strip():
                    sent_as_stream = await self._send_live_stream(
                        session_key,
                        msg.chat_id,
                        msg.content,
                        terminal=True,
                    )
                else:
                    await self._delete_live_preview(session_key)
                self._clear_live_session(session_key)
            if msg.content.strip() and not sent_as_stream:
                await self.send(msg.chat_id, msg.content)
            for image in msg.media:
                await self.send_image(msg.chat_id, image)
        except Exception:
            send_failed = True
            self._record_delivery_status(msg, "failed")
            raise
        finally:
            if not send_failed:
                self._record_delivery_status(msg, "sent")

    def _record_delivery_status(self, msg: OutboundMessage, status: str) -> None:
        if self._channel_hub is None:
            return
        self._channel_hub.mark_delivery(
            msg,
            default_channel=CHANNEL,
            delivery_status=status,
            external_message_id=str(msg.metadata.get("external_message_id") or ""),
        )

    async def send_proactive(self, chat_id: str, message: str) -> None:
        """Sends a proactive C2C text message through the official API."""
        await self.send(chat_id, message)

    async def send(self, chat_id: str, message: str) -> None:
        """Sends a normal Markdown message to a C2C target."""
        kind, target = self._parse_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("当前 QQBotChannel 仅支持私聊 c2c")
        token = await self._get_access_token()
        await self._api_request(
            "POST",
            f"/v2/users/{target}/messages",
            self._build_message_body(message),
            token,
        )

    async def send_image(self, chat_id: str, image: str) -> None:
        """Uploads and sends a PNG, JPEG, WebP, or animated GIF to C2C."""
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
        await self._api_request(
            "POST",
            f"/v2/users/{target}/messages",
            {
                "msg_type": 7,
                "media": {"file_info": file_info},
                "msg_seq": self._next_msg_seq(),
            },
            token,
        )

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

    async def send_stream(self, chat_id: str, message: str) -> None:
        """Sends a complete proactive response using the official stream API."""
        kind, target = self._parse_chat_id(chat_id)
        if kind != "c2c":
            raise ValueError("当前 QQBotChannel 仅支持私聊 c2c")
        msg_id = self._last_c2c_msg_id.get(target)
        if not msg_id:
            await self.send(chat_id, message)
            return
        try:
            await self._send_stream_c2c(target, msg_id, message)
        except Exception as exc:
            logger.warning("[qqbot] 私聊流式发送失败，回退普通发送: %s", exc)
            await self.send(chat_id, message)

    async def _send_stream_c2c(self, openid: str, msg_id: str, message: str) -> None:
        token = await self._get_access_token()
        msg_seq = self._next_msg_seq()
        stream_msg_id = ""
        chunks = iter_stream_chunks(message)
        for index, content in enumerate(chunks):
            body: dict[str, Any] = {
                "input_mode": "replace",
                "input_state": 10 if index == len(chunks) - 1 else 1,
                "content_type": "markdown",
                "content_raw": content,
                "event_id": msg_id,
                "msg_id": msg_id,
                "msg_seq": msg_seq,
                "index": index,
            }
            if stream_msg_id:
                body["stream_msg_id"] = stream_msg_id
            result = await self._api_request(
                "POST",
                f"/v2/users/{openid}/stream_messages",
                body,
                token,
            )
            stream_msg_id = str(result.get("id") or stream_msg_id)

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
