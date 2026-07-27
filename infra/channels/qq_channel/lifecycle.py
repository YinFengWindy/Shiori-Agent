from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, cast

from agent.looping.interrupt import InterruptController
from bus.event_bus import EventBus
from bus.events_lifecycle import ToolCallCompleted, ToolCallStarted, TurnStarted
from bus.queue import MessageBus
from core.channels import ChannelHub
from core.common.channel_identifiers import normalize_qq_group_chat_id
from core.net.http import HttpRequester, get_default_http_requester
from infra.channels.base import AttachmentStore, SessionIdentityIndex
from infra.channels.contract import ChannelContext
from infra.channels.group_filter import (
    DefaultGroupFilter,
    GroupMessageFilter,
    QQGroupFilterConfig,
    strip_at_segments,
)
from session.manager import SessionManager

from .compat import extract_cq_images, patch_ncatbot_ws_open_timeout
from .formatting import CHANNEL, _QQTraceState
from .inbound import _InboundMixin
from .loop_bridge import _LoopBridgeMixin
from .outbound import _OutboundMixin
from .trace import _TraceMixin

logger = logging.getLogger(__name__)


class QQChannel(_InboundMixin, _TraceMixin, _OutboundMixin, _LoopBridgeMixin):
    """Connects NcatBot private/group events to the shared message bus."""

    name = CHANNEL

    def __init__(
        self,
        bot_uin: str,
        bus: MessageBus,
        session_manager: SessionManager,
        allow_from: list[str] | None = None,
        groups: list[QQGroupFilterConfig] | None = None,
        websocket_open_timeout_seconds: float = 5.0,
        group_filter: GroupMessageFilter | None = None,
        http_requester: HttpRequester | None = None,
        event_bus: EventBus | None = None,
        interrupt_controller: InterruptController | None = None,
        channel_hub: ChannelHub | None = None,
    ) -> None:
        from ncatbot.core import BotClient
        from ncatbot.utils import ncatbot_config

        self._bus = bus
        self._session_manager = session_manager
        self._bot_uin = bot_uin
        allowed_users = [str(user_id) for user_id in (allow_from or [])]
        self._allow_from = set(allowed_users)
        self._websocket_open_timeout_seconds = float(websocket_open_timeout_seconds)
        self._interrupt_controller = interrupt_controller
        workspace = getattr(session_manager, "workspace", None)
        self._workspace = Path(workspace) if workspace else None
        self._attachments = AttachmentStore(
            Path(workspace) / "uploads" if workspace else None
        )
        self._channel_hub = channel_hub
        if self._channel_hub is None and workspace:
            self._channel_hub = ChannelHub.from_workspace(
                Path(workspace), session_manager=session_manager
            )
        self._trace_actor_name_cache: str | None = None
        self._identity_index = SessionIdentityIndex(
            session_manager, channel=CHANNEL, metadata_key="user_id"
        )
        self._groups = {group.group_id: group for group in groups or []}
        self._group_filter = group_filter or DefaultGroupFilter(bot_uin)
        self._http_requester = http_requester or get_default_http_requester(
            "external_default"
        )
        self._event_bus = event_bus
        self._outbound_bound = False
        self._events_bound = False
        self._trace_states: dict[str, _QQTraceState] = {}
        self._bot = BotClient()
        self._api = None
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._bot_loop: asyncio.AbstractEventLoop | None = None

        patch_ncatbot_ws_open_timeout(self._websocket_open_timeout_seconds)
        ncatbot_config.bt_uin = bot_uin
        ncatbot_config.root = allowed_users[0] if allowed_users else bot_uin
        ncatbot_config.check_ncatbot_update = False
        ncatbot_config.skip_ncatbot_install_check = True
        ncatbot_config.napcat.remote_mode = True
        ncatbot_config.napcat.enable_webui = False
        ncatbot_config.enable_webui_interaction = False
        # Resolve through the package entry point so existing monkeypatch callers work.
        from . import resolve_ncatbot_dir

        ncatbot_dir = resolve_ncatbot_dir()
        ncatbot_dir.mkdir(parents=True, exist_ok=True)
        (ncatbot_dir / "plugins").mkdir(exist_ok=True)
        ncatbot_config.plugin.plugins_dir = str(ncatbot_dir / "plugins")
        self.user_map = self._identity_index.mapping

    def _is_allowed(self, user_id: str) -> bool:
        return not self._allow_from or user_id in self._allow_from

    async def start(self, ctx: ChannelContext | None = None) -> None:
        if ctx is not None:
            self._bus = ctx.bus
            self._event_bus = ctx.event_bus
            self._interrupt_controller = ctx.interrupt_controller
            ctx.push_tool.register_channel(
                self.name,
                text=self.send,
                file=self.send_file,
                image=self.send_image,
            )
        self._main_loop = asyncio.get_running_loop()
        self._identity_index.rebuild()
        self._bind_events()

        @cast(Any, self._bot.on_private_message())
        async def _(event) -> None:
            if self._bot_loop is None:
                self._bot_loop = asyncio.get_running_loop()
            user_id = str(event.user_id)
            if not self._is_allowed(user_id):
                logger.warning("[qq] 拒绝未授权用户 user_id=%s", user_id)
                return
            text, image_urls = extract_cq_images(event.raw_message)
            if text.strip() == "/stop":
                self._submit_to_main_loop(self._handle_stop_private(user_id))
                return
            preview = text[:60] + "..." if len(text) > 60 else text
            logger.info(
                "[qq] 私聊消息 user_id=%s 内容: %r 图片: %d",
                user_id,
                preview,
                len(image_urls),
            )
            self.user_map[user_id] = user_id
            self._submit_to_main_loop(self._handle_private(user_id, text, image_urls))

        @cast(Any, self._bot.on_group_message())
        async def _(event) -> None:
            if self._bot_loop is None:
                self._bot_loop = asyncio.get_running_loop()
            group_id = str(event.group_id)
            user_id = str(event.user_id)
            group_config = self._groups.get(group_id)
            if group_config is None:
                chat_id = normalize_qq_group_chat_id(group_id)
                if self._channel_hub is None or not self._channel_hub.has_binding(
                    CHANNEL, chat_id
                ):
                    logger.debug("[qq] 忽略未绑定群 group_id=%s", group_id)
                    return
                group_config = QQGroupFilterConfig(group_id=group_id, require_at=True)
            future = asyncio.run_coroutine_threadsafe(
                self._group_filter.should_process(event, group_config),
                self._require_main_loop(),
            )
            if not future.result(timeout=5):
                return
            text, image_urls = extract_cq_images(strip_at_segments(event.raw_message))
            if text.strip() == "/stop":
                self._submit_to_main_loop(self._handle_stop_group(group_id, user_id))
                return
            preview = text[:60] + "..." if len(text) > 60 else text
            logger.info(
                "[qq] 群聊消息 group_id=%s user_id=%s 内容: %r 图片: %d",
                group_id,
                user_id,
                preview,
                len(image_urls),
            )
            self._submit_to_main_loop(
                self._handle_group(group_id, user_id, text, image_urls)
            )

        @cast(Any, self._bot.on_startup())
        async def _(_event) -> None:
            self._bot_loop = asyncio.get_running_loop()

        logger.info("[qq] 正在启动 NcatBot（首次运行需要扫码登录）...")
        self._api = await self._main_loop.run_in_executor(None, self._bot.run_backend)
        logger.info("[qq] NcatBot 已启动")
        if not self._outbound_bound:
            self._bus.subscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = True

    def _bind_events(self) -> None:
        if self._event_bus is None or self._events_bound:
            return
        self._event_bus.on(TurnStarted, self._on_turn_started)
        self._event_bus.on(ToolCallStarted, self._on_tool_call_started)
        self._event_bus.on(ToolCallCompleted, self._on_tool_call_completed)
        self._events_bound = True

    async def stop(self) -> None:
        if self._api:
            loop = asyncio.get_running_loop()
            bot_exit = getattr(self._bot, "exit", None)
            if callable(bot_exit):
                await loop.run_in_executor(None, bot_exit)
            logger.info("[qq] QQChannel 已停止")
