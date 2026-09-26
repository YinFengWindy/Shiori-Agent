from __future__ import annotations

import logging

from bus.events import OutboundMessage
from infra.channels.session_key import resolve_outbound_session_key

from .compat import is_local, local_to_base64
from .formatting import CHANNEL, GROUP_PREFIX

logger = logging.getLogger(__name__)


class _OutboundMixin:
    """Owns NcatBot text, file, image, trace, and delivery output."""

    async def _on_response(self, msg: OutboundMessage) -> None:
        preview = msg.content[:60] + "..." if len(msg.content) > 60 else msg.content
        api = self._api
        if api is None:
            raise RuntimeError("QQChannel 尚未启动")
        session_key = resolve_outbound_session_key(msg, default_channel=CHANNEL)
        if not msg.chat_id.startswith(GROUP_PREFIX):
            try:
                await self._send_private_trace(msg.chat_id, session_key, msg)
            except Exception as exc:
                logger.warning(
                    "[qq] 私聊 tracing 合并转发失败 chat_id=%s 错误: %s",
                    msg.chat_id,
                    exc,
                )
        first_id: str | None = None
        if msg.content.strip():
            try:
                logger.info("[qq] 回复 chat_id=%s 内容: %r", msg.chat_id, preview)
                first_id = await self.send(msg.chat_id, msg.content)
            except BaseException as exc:
                self._record_delivery_status(
                    msg, delivery_status="failed", external_message_id=first_id
                )
                logger.error("[qq] 发送失败 chat_id=%s 错误: %s", msg.chat_id, exc)
                raise
        for image in msg.media or []:
            try:
                image_id = await self.send_image(msg.chat_id, image)
                first_id = first_id or image_id
            except BaseException as exc:
                self._record_delivery_status(
                    msg, delivery_status="failed", external_message_id=first_id
                )
                logger.error(
                    "[qq] meme 图片发送失败 chat_id=%s path=%s err=%s",
                    msg.chat_id,
                    image,
                    exc,
                )
                raise
        self._record_delivery_status(
            msg, delivery_status="sent", external_message_id=first_id
        )
        self._trace_states.pop(session_key, None)

    async def send(self, chat_id: str, message: str) -> str | None:
        """发送文本消息，自动区分私聊/群聊；返回 NapCat 分配的消息 id。"""
        api = self._require_api()
        if chat_id.startswith(GROUP_PREFIX):
            sent = await self._run_on_bot_loop(
                api.send_group_text(int(chat_id[len(GROUP_PREFIX) :]), message)
            )
        else:
            sent = await self._run_on_bot_loop(
                api.send_private_text(int(chat_id), message)
            )
        return _sent_message_id(sent)

    async def send_file(
        self, chat_id: str, file_path: str, name: str | None = None
    ) -> None:
        """发送文件，自动区分私聊/群聊。"""
        api = self._require_api()
        uri = local_to_base64(file_path) if is_local(file_path) else file_path
        if chat_id.startswith(GROUP_PREFIX):
            await self._run_on_bot_loop(
                api.send_group_file(int(chat_id[len(GROUP_PREFIX) :]), uri, name)
            )
        else:
            await self._run_on_bot_loop(api.send_private_file(int(chat_id), uri, name))

    async def send_image(self, chat_id: str, image: str) -> str | None:
        """发送图片，自动区分私聊/群聊；返回 NapCat 分配的消息 id。"""
        api = self._require_api()
        uri = local_to_base64(image) if is_local(image) else image
        if chat_id.startswith(GROUP_PREFIX):
            sent = await self._run_on_bot_loop(
                api.send_group_image(int(chat_id[len(GROUP_PREFIX) :]), uri)
            )
        else:
            sent = await self._run_on_bot_loop(
                api.send_private_image(int(chat_id), uri)
            )
        return _sent_message_id(sent)

    def _require_api(self):
        if self._api is None:
            raise RuntimeError("QQChannel 尚未启动")
        return self._api

    def _record_delivery_status(
        self,
        msg: OutboundMessage,
        *,
        delivery_status: str,
        external_message_id: str | None = None,
    ) -> None:
        if self._channel_hub is not None:
            self._channel_hub.mark_delivery(
                msg,
                default_channel=CHANNEL,
                delivery_status=delivery_status,
                external_message_id=external_message_id or "",
            )


def _sent_message_id(sent: object) -> str | None:
    """NcatBot send APIs return the message id; None means it reported none.

    Any other shape is an unexpected API contract change: fail instead of
    storing a stringified object as the platform id.
    """
    if sent is None:
        return None
    if isinstance(sent, (str, int)) and not isinstance(sent, bool):
        return str(sent)
    raise TypeError(f"NcatBot 返回了无法识别的消息 id: {sent!r}")
