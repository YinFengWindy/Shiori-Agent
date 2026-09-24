"""TelegramChannel 初始化与运行时生命周期。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from agent.looping.interrupt import InterruptController
from bus.event_bus import EventBus
from bus.event_binding import EventBinding
from bus.events_lifecycle import (
    StreamDeltaReady,
    ToolCallCompleted,
    ToolCallStarted,
    TurnStarted,
)
from bus.queue import MessageBus
from core.channels import ChannelHub
from infra.channels.base import AttachmentStore, MessageDeduper, SessionIdentityIndex
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake
from session.manager import SessionManager

from ..utils import (
    TelegramLiveEditQueue,
    TelegramLiveTextMessage,
    TelegramOutboundLimiter,
    TelegramStreamMessage,
)
from .commands import _CommandMixin
from .formatting import (
    _CHANNEL,
    _RENDERING_PROMPT,
    _SEEN_MSG_MAXSIZE,
    _ToolLiveLine,
    _is_private_chat_id,
)
from .inbound import _InboundMixin
from .media import _MediaMixin
from .outbound import _OutboundMixin
from .streaming import _StreamingMixin

logger = logging.getLogger("plugins.telegram.channel")


class TelegramChannel(
    _InboundMixin,
    _CommandMixin,
    _MediaMixin,
    _StreamingMixin,
    _OutboundMixin,
):
    """连接 Telegram Bot、消息总线与 lifecycle 事件。"""

    # Inbound handlers always annotate chat_type; this only covers omissions.
    default_chat_type = "private"

    name = _CHANNEL
    # start() registers ctx.bot_commands with BotFather's command menu.
    uses_bot_commands = True

    def __init__(
        self,
        token: str,
        bus: MessageBus | None = None,
        session_manager: SessionManager | None = None,
        allow_from: list[str] | None = None,
        bot_commands: list[tuple[str, str]] | None = None,
        event_bus: EventBus | None = None,
        interrupt_controller: InterruptController | None = None,
        channel_hub: "ChannelHub | None" = None,
    ) -> None:
        # bus / session_manager 在宿主里由 start(ctx) 注入；构造参数只留给
        # 不经 ChannelHost 直接驱动渠道的测试。
        self._token = token
        self._bus: MessageBus | None = bus
        self._interrupt_controller = interrupt_controller
        self._channel = _CHANNEL
        self._allow_from: set[str] = set(allow_from) if allow_from else set()
        self._message_deduper = MessageDeduper(_SEEN_MSG_MAXSIZE)
        self._channel_hub = channel_hub
        self._session_manager: SessionManager | None = None
        self._attachments = AttachmentStore()
        self._identity_index: SessionIdentityIndex | None = None
        self.user_map: dict[str, str] = {}
        if session_manager is not None:
            self._bind_session_manager(session_manager)
        self._app = Application.builder().token(token).build()
        self._bot_commands = bot_commands or []
        self._app.add_handler(CommandHandler("stop", self._on_stop_command))
        self._app.add_handler(MessageHandler(filters.COMMAND, self._on_command))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self._app.add_handler(
            MessageHandler(filters.PHOTO & ~filters.COMMAND, self._on_photo)
        )
        self._app.add_handler(
            MessageHandler(filters.Document.ALL & ~filters.COMMAND, self._on_document)
        )
        self._event_bus = event_bus
        self._outbound_bound = False
        self._events_bound = False
        self._push_tool = None
        self._intake = ChannelIntake(self._accept_inbound, self.send)
        self._event_bindings = (
            EventBinding(TurnStarted, self._on_turn_started),
            EventBinding(StreamDeltaReady, self._on_stream_delta),
            EventBinding(ToolCallStarted, self._on_tool_call_started),
            EventBinding(ToolCallCompleted, self._on_tool_call_completed),
        )
        self._polling_conflict_task: asyncio.Task[None] | None = None
        self._telegram_outbound_limiter = TelegramOutboundLimiter()
        self._active_streams: dict[str, TelegramStreamMessage] = {}
        self._live_edit_queue = TelegramLiveEditQueue(
            limiter=self._telegram_outbound_limiter
        )
        self._live_messages: dict[str, TelegramLiveTextMessage] = {}
        self._reply_buffers: dict[str, str] = {}
        self._thinking_buffers: dict[str, str] = {}
        self._thinking_live_next_at: dict[str, float] = {}
        self._live_last_lengths: dict[str, int] = {}
        self._tool_lines: dict[str, list[_ToolLiveLine]] = {}
        self._live_tasks: set[asyncio.Task[None]] = set()
        self._live_tasks_by_session: dict[str, set[asyncio.Task[None]]] = {}

    @property
    def bot(self):
        return self._app.bot

    def supports_stream_events(self, chat_id: str) -> bool:
        """Streams live previews only into private chats."""
        return _is_private_chat_id(chat_id)

    def system_prompt_hint(self, chat_id: str) -> str:
        """Forbids Markdown tables, which Telegram mobile cannot render."""
        return _RENDERING_PROMPT

    @property
    def configuration_key(self) -> tuple[str, str]:
        """Reuses the polling connection across generations while the token holds.

        The host adds the bot command list to this key, so changed commands
        rebuild the connection just like a changed token.
        """
        return ("telegram", self._token)

    async def start(self, ctx: ChannelContext | None = None) -> None:
        self._intake.start(paused=ctx.intake_paused if ctx is not None else False)
        if ctx is not None:
            self._bus = ctx.bus
            self._event_bus = ctx.event_bus
            self._interrupt_controller = ctx.interrupt_controller
            self._push_tool = ctx.push_tool
            # 启动时的命令列表随连接固定；命令变化由宿主的复用键触发重建。
            self._bot_commands = list(ctx.bot_commands)
            if ctx.channel_hub is not None:
                self._channel_hub = ctx.channel_hub
            if self._session_manager is not ctx.session_manager:
                self._bind_session_manager(ctx.session_manager)
            ctx.push_tool.register_channel(
                self.name,
                text=self.send,
                stream_text=self.send_stream,
                file=self.send_file,
                image=self.send_image,
                target_resolver=self._resolve_chat_id,
            )
        self._bind_runtime()
        self._rebuild_user_map()
        await self._app.initialize()
        await self._app.start()
        await self._register_bot_commands()
        updater = self._app.updater
        if updater is None:
            raise RuntimeError("Telegram updater 未初始化")
        await updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            error_callback=self._on_polling_error,
        )
        logger.info(f"TelegramChannel 已启动  已知用户: {len(self.user_map)}")

    def _bind_session_manager(self, session_manager: SessionManager) -> None:
        """Binds workspace-backed state: uploads, username index and fallback hub."""
        self._session_manager = session_manager
        ws = getattr(session_manager, "workspace", None)
        self._attachments = AttachmentStore(Path(ws) / "uploads" if ws else None)
        if self._channel_hub is None and ws:
            self._channel_hub = ChannelHub.from_workspace(
                Path(ws),
                session_manager=session_manager,
            )
        self._identity_index = SessionIdentityIndex(
            session_manager,
            channel=self._channel,
            metadata_key="username",
            normalizer=lambda value: value.lower(),
        )
        self.user_map = self._identity_index.mapping

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise RuntimeError("TelegramChannel 尚未启动")
        return self._bus

    def _require_identity_index(self) -> SessionIdentityIndex:
        if self._identity_index is None:
            raise RuntimeError("TelegramChannel 尚未绑定会话")
        return self._identity_index

    def _bind_runtime(self) -> None:
        if not self._outbound_bound:
            self._require_bus().subscribe_outbound(self._channel, self._on_response)
            self._outbound_bound = True
        if self._event_bus is not None and not self._events_bound:
            for binding in self._event_bindings:
                binding.bind(self._event_bus)
            self._events_bound = True

    async def stop(self) -> None:
        """Stops intake and releases owned subscriptions, including partial starts."""
        self._intake.pause()
        try:
            await self._stop_connection()
        finally:
            self._unbind_runtime()

    def pause_intake(self) -> None:
        """Buffers new incoming turns while keeping accepted replies deliverable."""
        self._intake.pause()

    def resume_intake(self) -> None:
        """Restores intake after a rejected channel removal."""
        self._intake.resume()

    def _unbind_runtime(self) -> None:
        if self._outbound_bound:
            self._require_bus().unsubscribe_outbound(self._channel, self._on_response)
            self._outbound_bound = False
        if self._event_bus is not None and self._events_bound:
            for binding in self._event_bindings:
                binding.unbind(self._event_bus)
            self._events_bound = False
        if self._push_tool is not None:
            self._push_tool.unregister_channel(self.name, text=self.send)

    async def _stop_connection(self) -> None:
        if self._polling_conflict_task and not self._polling_conflict_task.done():
            await self._polling_conflict_task
        if self._live_tasks:
            _ = await asyncio.gather(*self._live_tasks, return_exceptions=True)
        updater = self._app.updater
        if updater and updater.running:
            await updater.stop()
        if self._app.running:
            await self._app.stop()
        await self._intake.close()
        await self._app.shutdown()
        logger.info("TelegramChannel 已停止")

    # ── 私有方法 ──────────────────────────────────────────────────

    def _rebuild_user_map(self) -> None:
        """扫描已有 session 文件，从 metadata 重建 username → chat_id 索引。"""
        self._require_identity_index().rebuild()
        logger.debug(f"[telegram] user_map 重建完成: {self.user_map}")

    def _is_allowed(self, user) -> bool:
        """检查用户是否在白名单中，白名单为空则允许所有人"""
        if not self._allow_from:
            return True
        return str(user.id) in self._allow_from or (
            user.username
            and user.username.lower() in {u.lower() for u in self._allow_from}
        )

    async def _register_bot_commands(self) -> None:
        commands = [
            BotCommand(command, description)
            for command, description in [
                *self._bot_commands,
                ("stop", "中断当前回复"),
            ]
        ]
        await self._app.bot.set_my_commands(commands)

    async def _remember_username(self, chat_id: str, username: str | None) -> None:
        if username:
            await self._require_identity_index().remember(username, chat_id)
