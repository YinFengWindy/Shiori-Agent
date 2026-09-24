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
        send_failed = False
        if msg.content.strip():
            try:
                if msg.chat_id.startswith(GROUP_PREFIX):
                    group_id = msg.chat_id[len(GROUP_PREFIX) :]
                    logger.info("[qq] 群聊回复 group_id=%s 内容: %r", group_id, preview)
                    await self._run_on_bot_loop(
                        api.send_group_text(int(group_id), msg.content)
                    )
                else:
                    logger.info(
                        "[qq] 私聊回复 user_id=%s 内容: %r", msg.chat_id, preview
                    )
                    await self._run_on_bot_loop(
                        api.send_private_text(int(msg.chat_id), msg.content)
                    )
            except Exception as exc:
                send_failed = True
                self._record_delivery_status(msg, delivery_status="failed")
                logger.error("[qq] 发送失败 chat_id=%s 错误: %s", msg.chat_id, exc)
                raise
        for image in msg.media or []:
            try:
                await self.send_image(msg.chat_id, image)
            except Exception as exc:
                send_failed = True
                self._record_delivery_status(msg, delivery_status="failed")
                logger.error(
                    "[qq] meme 图片发送失败 chat_id=%s path=%s err=%s",
                    msg.chat_id,
                    image,
                    exc,
                )
                raise
        if not send_failed:
            self._record_delivery_status(msg, delivery_status="sent")
        self._trace_states.pop(session_key, None)

    async def send(self, chat_id: str, message: str) -> None:
        """发送文本消息，自动区分私聊/群聊。"""
        api = self._require_api()
        if chat_id.startswith(GROUP_PREFIX):
            await self._run_on_bot_loop(
                api.send_group_text(int(chat_id[len(GROUP_PREFIX) :]), message)
            )
        else:
            await self._run_on_bot_loop(api.send_private_text(int(chat_id), message))

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

    async def send_image(self, chat_id: str, image: str) -> None:
        """发送图片，自动区分私聊/群聊。"""
        api = self._require_api()
        uri = local_to_base64(image) if is_local(image) else image
        if chat_id.startswith(GROUP_PREFIX):
            await self._run_on_bot_loop(
                api.send_group_image(int(chat_id[len(GROUP_PREFIX) :]), uri)
            )
        else:
            await self._run_on_bot_loop(api.send_private_image(int(chat_id), uri))

    def _require_api(self):
        if self._api is None:
            raise RuntimeError("QQChannel 尚未启动")
        return self._api

    def _record_delivery_status(
        self, msg: OutboundMessage, *, delivery_status: str
    ) -> None:
        if self._channel_hub is not None:
            self._channel_hub.mark_delivery(
                msg,
                default_channel=CHANNEL,
                delivery_status=delivery_status,
            )
