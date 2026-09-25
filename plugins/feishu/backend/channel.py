"""Feishu / Lark private-chat channel: lifecycle, routing and delivery."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from agent.looping.interrupt import InterruptController
from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import StreamDeltaReady, TurnStarted
from bus.queue import MessageBus
from core.channels import ChannelHub
from core.common.channel_chat_types import (
    ChatTypeDeclaration,
    chat_id_command_reply,
    is_chat_id_command,
)
from infra.channels.contract import ChannelContext, ChannelStatus
from infra.channels.intake import ChannelIntake
from infra.channels.session_key import resolve_outbound_session_key

from .api import FeishuApi, is_rate_limited, with_rate_limit_retry
from .dedupe import ExpiringIdSet
from .formatting import (
    CHANNEL,
    PUSH_TARGET_HINT,
    SYSTEM_PROMPT_HINT,
    markdown_card,
    split_markdown,
)
from .inbound import InboundResolver, ReceivedMessage, parse_receive_event
from .streaming import LiveCardStreamer
from .ws import (
    ConnectionFactory,
    ConnectionState,
    LongConnectionRunner,
    sdk_connection_factory,
)

logger = logging.getLogger(__name__)

STOP_COMMAND = "/stop"
PENDING_QUOTES_PER_SESSION = 16


class FeishuChannel:
    """Receives private chats over the long connection and replies over REST.

    Threading: the lark-oapi long connection runs on its own thread (see
    ``ws.py``); its event callback only deduplicates and hands the event to
    this channel's event loop, so Feishu gets its acknowledgement at once and
    all downloads, routing and replies run on the host loop.
    """

    name = CHANNEL
    default_chat_type = "private"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        connection_factory: ConnectionFactory | None = None,
        chat_types: tuple[ChatTypeDeclaration, ...] = (),
    ) -> None:
        self._app_id = app_id
        # The manifest's session types, for answering ``/chatid``.
        self._chat_types = chat_types
        self._app_secret = app_secret
        self._domain = domain
        self._api = FeishuApi(app_id, app_secret, domain, transport=transport)
        self._connection_factory = connection_factory or sdk_connection_factory(
            app_id, app_secret, domain
        )
        self._streamer = LiveCardStreamer(self._api, self._send_live_card)
        self._intake = ChannelIntake(self._accept_inbound, self.send)
        self._seen = ExpiringIdSet()
        self._runner: LongConnectionRunner | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._event_bus: EventBus | None = None
        self._push_tool: MessagePushTool | None = None
        self._channel_hub: ChannelHub | None = None
        self._interrupt_controller: InterruptController | None = None
        self._resolver: InboundResolver | None = None
        self._inbound_tasks: set[asyncio.Task[None]] = set()
        self._accepting = False
        self._outbound_bound = False
        self._events_bound = False
        self._push_registered = False
        self._bot_name = ""
        self._last_unbound = ""
        # Accepted inbound message ids per session, keyed by the inbound
        # timestamp that the turn's ``TurnStarted`` event carries over.
        self._pending_quotes: dict[str, dict[datetime, str]] = {}
        self._event_bindings = [
            (TurnStarted, self._on_turn_started),
            (StreamDeltaReady, self._on_stream_delta),
        ]

    @property
    def configuration_key(self):
        """Identifies connections reusable across plugin generations."""
        return (
            "feishu",
            self._app_id,
            self._app_secret,
            self._domain,
        )

    # ── channel hooks ────────────────────────────────────────────────

    def supports_stream_events(self, chat_id: str) -> bool:
        """Private chats render the reply live in a CardKit streaming card."""
        return bool(chat_id.strip())

    def system_prompt_hint(self, chat_id: str) -> str:
        """Tells the model what a Feishu card can render."""
        return SYSTEM_PROMPT_HINT

    def status(self) -> ChannelStatus:
        """Reports the long connection, the bot name and the last unbound sender."""
        state = (
            self._runner.state
            if self._runner is not None
            else ConnectionState(False, "未启动")
        )
        result: ChannelStatus = {"connected": state.connected}
        if self._bot_name:
            result["account"] = self._bot_name
        detail = state.detail
        if self._last_unbound:
            detail = f"{detail}；{self._last_unbound}"
        result["detail"] = detail
        return result

    # ── lifecycle ────────────────────────────────────────────────────

    async def start(self, ctx: ChannelContext) -> None:
        """Registers delivery hooks and starts the long-connection thread."""
        if importlib.util.find_spec("lark_oapi") is None:
            raise RuntimeError("飞书渠道缺少依赖 lark-oapi")
        self._loop = asyncio.get_running_loop()
        self._bus = ctx.bus
        self._event_bus = ctx.event_bus
        self._push_tool = ctx.push_tool
        self._channel_hub = ctx.channel_hub
        self._interrupt_controller = ctx.interrupt_controller
        self._resolver = InboundResolver(self._api, ctx.attachment_store)
        self._api.open()
        if not self._events_bound:
            for event_type, handler in self._event_bindings:
                ctx.event_bus.on(event_type, handler)
            self._events_bound = True
        ctx.push_tool.register_channel(
            self.name,
            text=self.send,
            file=self.send_file,
            image=self.send_image,
            description=PUSH_TARGET_HINT,
        )
        self._push_registered = True
        if not self._outbound_bound:
            ctx.bus.subscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = True
        self._intake.start(paused=ctx.intake_paused)
        self._accepting = True
        self._runner = LongConnectionRunner(
            self._connection_factory,
            self._on_ws_event,
            on_state=self._on_connection_state,
        )
        self._runner.start()
        logger.info("[feishu] 飞书渠道已启动")

    async def stop(self) -> None:
        """Stops intake first, then the connection, then pending work.

        Order matters: sources of new work (long connection, stream events)
        are cut before their task sets are drained, so nothing spawns a task
        after the drain snapshot. Safe on a never-started instance and when
        called repeatedly.
        """
        self.pause_intake()
        self._accepting = False
        if self._event_bus is not None and self._events_bound:
            for event_type, handler in self._event_bindings:
                self._event_bus.off(event_type, handler)
            self._events_bound = False
        if self._runner is not None:
            await self._runner.stop()
        tasks = [task for task in self._inbound_tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._streamer.close()
        await self._intake.close()
        if self._bus is not None and self._outbound_bound:
            self._bus.unsubscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = False
        if self._push_tool is not None and self._push_registered:
            self._push_tool.unregister_channel(self.name, text=self.send)
            self._push_registered = False
        await self._api.aclose()
        logger.info("[feishu] 飞书渠道已停止")

    def pause_intake(self) -> None:
        """Buffers incoming turns while existing replies remain deliverable."""
        self._intake.pause()

    def resume_intake(self) -> None:
        """Restores intake after a rejected settings transaction."""
        self._intake.resume()

    # ── inbound (long-connection thread) ─────────────────────────────

    def _on_ws_event(self, envelope: dict[str, Any]) -> None:
        """Runs on the long-connection thread; must return well within 3 s."""
        message = parse_receive_event(envelope)
        if message is None:
            return
        if self._seen.seen(message.event_id, message.message_id):
            logger.debug("[feishu] 忽略重复投递 message_id=%s", message.message_id)
            return
        if message.chat_type != "p2p":
            logger.debug("[feishu] 仅支持私聊，忽略 chat_type=%s", message.chat_type)
            return
        loop = self._loop
        if loop is None or not self._accepting:
            return
        try:
            loop.call_soon_threadsafe(self._spawn_inbound, message)
        except RuntimeError:
            logger.debug("[feishu] 事件循环已关闭，丢弃消息")

    def _on_connection_state(self, state: ConnectionState) -> None:
        loop = self._loop
        if not state.connected or self._bot_name or loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._spawn_bot_info)
        except RuntimeError:
            pass

    # ── inbound (event loop) ─────────────────────────────────────────

    def _spawn_inbound(self, message: ReceivedMessage) -> None:
        if self._accepting:
            self._track(self._handle_message(message))

    def _spawn_bot_info(self) -> None:
        if self._accepting and not self._bot_name:
            self._track(self._load_bot_info())

    def _track(self, coro: Any) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coro)
        self._inbound_tasks.add(task)
        task.add_done_callback(self._on_inbound_done)

    def _on_inbound_done(self, task: asyncio.Task[None]) -> None:
        self._inbound_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("[feishu] 处理入站消息失败: %s", task.exception())

    async def _load_bot_info(self) -> None:
        try:
            info = await self._api.bot_info()
        except Exception as error:
            logger.debug("[feishu] 读取机器人信息失败: %s", error)
            return
        self._bot_name = str(info.get("app_name") or "")

    async def _handle_message(self, message: ReceivedMessage) -> None:
        if message.sender_type and message.sender_type != "user":
            return
        sender = message.sender_open_id
        if not sender:
            return
        text = ""
        if message.message_type == "text":
            text = str(message.content.get("text") or "").strip()
        if is_chat_id_command(text):
            await self._handle_chat_id(message.chat_id, sender)
            return
        # Admission before resolving the payload, which downloads attachments.
        if not self._is_bound(message.chat_id, sender):
            return
        if text == STOP_COMMAND:
            await self._handle_stop(message.chat_id, sender)
            return
        if self._resolver is None:
            return
        payload = await self._resolver.resolve(message)
        if not payload.text and not payload.media:
            return
        await self._intake.submit(
            InboundMessage(
                channel=CHANNEL,
                sender=sender,
                chat_id=message.chat_id,
                content=payload.text,
                media=payload.media,
                metadata={
                    "chat_type": "private",
                    "open_id": sender,
                    "message_id": message.message_id,
                    "message_type": message.message_type,
                    "external_message_id": message.message_id,
                    **payload.metadata,
                },
            )
        )

    async def _accept_inbound(self, message: InboundMessage) -> None:
        if self._channel_hub is not None:
            if not self._is_bound(message.chat_id, message.sender):
                return
            message = self._channel_hub.route_inbound(message)
        if message.metadata.get("conversation_duplicate"):
            return
        self._remember_quote(message)
        await self._require_bus().publish_inbound(message)

    def _remember_quote(self, message: InboundMessage) -> None:
        """Keeps the user message a reply to this inbound turn should quote."""
        message_id = str(message.metadata.get("message_id") or "")
        if not message_id:
            return
        pending = self._pending_quotes.setdefault(message.session_key, {})
        pending[message.timestamp] = message_id
        while len(pending) > PENDING_QUOTES_PER_SESSION:
            pending.pop(next(iter(pending)))

    def _is_bound(self, chat_id: str, sender: str) -> bool:
        hub = self._channel_hub
        if hub is None or hub.is_sender_allowed(
            channel=CHANNEL, chat_id=chat_id, sender_id=sender
        ):
            return True
        # Shown in the channel status so the user can copy the ids to bind.
        self._last_unbound = f"未绑定的私聊：chat_id={chat_id}，open_id={sender}"
        logger.warning(
            "[feishu] 拒绝未绑定渠道的消息 chat_id=%s open_id=%s",
            chat_id,
            sender,
        )
        return False

    async def _handle_chat_id(self, chat_id: str, sender: str) -> None:
        """Answers ``/chatid`` with what the binding form asks for this chat."""
        if not self._may_answer_chat_id(chat_id, sender):
            return
        await self.send(
            chat_id, chat_id_command_reply(chat_id, "private", self._chat_types)
        )

    def _may_answer_chat_id(self, chat_id: str, sender: str) -> bool:
        """Admission for ``/chatid``: everyone except a bound session's blacklist.

        The one deliberate exception to "a rejected message has no side
        effect": ``/chatid`` is answered in a chat that is not bound yet,
        because it is how the user finds the chat_id to bind. A blacklisted
        sender still gets no reply and causes nothing.
        """
        hub = self._channel_hub
        if hub is None or not hub.is_sender_blocked(
            channel=CHANNEL, chat_id=chat_id, sender_id=sender
        ):
            return True
        logger.warning("[feishu] 忽略黑名单成员的 /chatid chat_id=%s", chat_id)
        return False

    async def _handle_stop(self, chat_id: str, sender: str) -> None:
        if self._interrupt_controller is None:
            await self.send(chat_id, "当前未启用中断功能。")
            return
        session_key = (
            self._channel_hub.resolve_runtime_session_key(CHANNEL, chat_id)
            if self._channel_hub is not None
            else f"{CHANNEL}:{chat_id}"
        )
        result = self._interrupt_controller.request_interrupt(
            session_key=session_key,
            sender=sender,
            command=STOP_COMMAND,
        )
        await self.send(chat_id, result.message)

    # ── streaming ────────────────────────────────────────────────────

    async def _on_turn_started(self, event: TurnStarted) -> None:
        if event.channel != CHANNEL:
            return
        # Only a turn started by an accepted inbound message quotes it;
        # proactive and scheduled turns carry no matching timestamp.
        quote = self._pending_quotes.get(event.session_key, {}).pop(
            event.timestamp, None
        )
        await self._streamer.begin_turn(event.session_key, quote=quote)

    async def _on_stream_delta(self, event: StreamDeltaReady) -> None:
        if event.channel == CHANNEL and event.content_delta:
            self._streamer.add_delta(
                event.session_key, event.chat_id, event.content_delta
            )

    async def _send_live_card(
        self, chat_id: str, content: str, quote: str | None
    ) -> str:
        return await self._deliver(chat_id, "interactive", content, quote)

    # ── outbound ─────────────────────────────────────────────────────

    async def _on_response(self, msg: OutboundMessage) -> None:
        session_key = resolve_outbound_session_key(msg, default_channel=CHANNEL)
        try:
            remaining = await self._streamer.finish(session_key, msg.content)
            if remaining is None:
                await self._send_text(
                    msg.chat_id, msg.content, reply_to=quoted_message_id(msg)
                )
            elif remaining.strip():
                await self._send_text(msg.chat_id, remaining)
            for image in msg.media:
                await self.send_image(msg.chat_id, image)
        except Exception:
            self._record_delivery_status(msg, "failed")
            raise
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

    async def send(self, chat_id: str, message: str) -> None:
        """Sends Markdown as one or more cards (plain text if a card fails)."""
        await self._send_text(chat_id, message)

    async def _send_text(
        self, chat_id: str, text: str, *, reply_to: str | None = None
    ) -> None:
        if not text.strip():
            return
        for index, chunk in enumerate(split_markdown(text.strip())):
            await self._send_chunk(chat_id, chunk, reply_to if index == 0 else None)

    async def _send_chunk(self, chat_id: str, chunk: str, reply_to: str | None) -> None:
        try:
            await self._deliver(chat_id, "interactive", markdown_card(chunk), reply_to)
        except Exception as error:
            if is_rate_limited(error):
                raise
            logger.warning("[feishu] 卡片发送失败，改发纯文本: %s", error)
            content = json.dumps({"text": chunk}, ensure_ascii=False)
            await self._deliver(chat_id, "text", content, reply_to)

    async def _deliver(
        self, chat_id: str, msg_type: str, content: str, reply_to: str | None
    ) -> str:
        """Sends one message, as a quoting reply when ``reply_to`` is given.

        A reply the API refuses (e.g. the quoted message was recalled) is
        sent again as a plain message so the content is not lost.
        """
        receive_id, receive_id_type = resolve_receive_id(chat_id)

        async def send() -> str:
            return await self._api.send_message(
                receive_id, receive_id_type, msg_type, content
            )

        label = f"发送{msg_type}消息"
        if not reply_to:
            return await with_rate_limit_retry(send, label=label)
        quoted = reply_to

        async def reply() -> str:
            return await self._api.reply_message(quoted, msg_type, content)

        try:
            return await with_rate_limit_retry(reply, label=label)
        except Exception as error:
            if is_rate_limited(error):
                raise
            logger.warning("[feishu] 引用回复失败，改为普通发送: %s", error)
            return await with_rate_limit_retry(send, label=label)

    async def send_image(self, chat_id: str, image: str) -> None:
        """Uploads and sends an image from a local path or an http(s) URL."""
        source = image.strip()
        if source.startswith(("http://", "https://")):
            data = await self._api.fetch_url(source)
        else:
            data = Path(source).expanduser().read_bytes()
        image_key = await self._api.upload_image(data)
        await self._deliver(
            chat_id, "image", json.dumps({"image_key": image_key}), None
        )

    async def send_file(
        self, chat_id: str, file_path: str, name: str | None = None
    ) -> None:
        """Uploads and sends a local file."""
        path = Path(file_path).expanduser()
        file_key = await self._api.upload_file(path.read_bytes(), name or path.name)
        await self._deliver(chat_id, "file", json.dumps({"file_key": file_key}), None)

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise RuntimeError("FeishuChannel 尚未启动")
        return self._bus


def quoted_message_id(msg: OutboundMessage) -> str | None:
    """Returns the user message a final reply quotes, if it answers one.

    Replies of inbound turns carry the triggering message's metadata; proactive
    and scheduled outbound messages do not and are sent without a quote.
    """
    if msg.reply_to:
        return msg.reply_to
    metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
    message_id = str(metadata.get("message_id") or "").strip()
    return message_id if message_id.startswith("om_") else None


def resolve_receive_id(chat_id: str) -> tuple[str, str]:
    """Maps a stored chat id (or an open/union id) to ``receive_id_type``."""
    value = chat_id.strip()
    if value.startswith(f"{CHANNEL}:"):
        value = value[len(CHANNEL) + 1 :]
    if value.startswith("ou_"):
        return value, "open_id"
    if value.startswith("on_"):
        return value, "union_id"
    return value, "chat_id"
