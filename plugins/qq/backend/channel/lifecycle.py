from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, cast

from agent.looping.interrupt import InterruptController
from bus.event_bus import EventBus
from bus.event_binding import EventBinding
from bus.events_lifecycle import ToolCallCompleted, ToolCallStarted, TurnStarted
from bus.queue import MessageBus
from core.channels import ChannelHub
from core.common.channel_identifiers import normalize_qq_group_chat_id
from core.common.workspace import resolve_ncatbot_dir
from core.net.http import HttpRequester, get_default_http_requester
from infra.channels.base import AttachmentStore, SessionIdentityIndex
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake
from session.manager import SessionManager

from .compat import (
    apply_napcat_connection,
    extract_cq_images,
    patch_ncatbot_ws_open_timeout,
)
from .formatting import CHANNEL, PUSH_TARGET_HINT, _QQTraceState
from .group_filter import (
    DefaultGroupFilter,
    GroupMessageFilter,
    QQGroupFilterConfig,
    strip_at_segments,
)
from .inbound import _InboundMixin
from .loop_bridge import _LoopBridgeMixin
from .outbound import _OutboundMixin
from .trace import _TraceMixin
from .sdk_runtime import QQSdkRuntime

logger = logging.getLogger(__name__)


class QQChannel(_InboundMixin, _TraceMixin, _OutboundMixin, _LoopBridgeMixin):
    """Connects NcatBot private/group events to the shared message bus."""

    name = CHANNEL

    def __init__(
        self,
        bot_uin: str,
        bus: MessageBus | None = None,
        session_manager: SessionManager | None = None,
        groups: list[QQGroupFilterConfig] | None = None,
        websocket_open_timeout_seconds: float = 5.0,
        group_filter: GroupMessageFilter | None = None,
        http_requester: HttpRequester | None = None,
        event_bus: EventBus | None = None,
        interrupt_controller: InterruptController | None = None,
        channel_hub: ChannelHub | None = None,
        ws_uri: str = "",
        ws_token: str = "",
    ) -> None:
        # bus / session_manager / HTTP 在宿主里由 start(ctx) 注入；构造参数只留给
        # 不经 ChannelHost 直接驱动渠道的测试。
        self._bus: MessageBus | None = bus
        self._bot_uin = bot_uin
        self._websocket_open_timeout_seconds = float(websocket_open_timeout_seconds)
        # 空值表示沿用 NcatBot 自己的默认值（或其 config.yaml）。
        self._ws_uri = ws_uri
        self._ws_token = ws_token
        self._interrupt_controller = interrupt_controller
        self._channel_hub = channel_hub
        self._session_manager: SessionManager | None = None
        self._workspace: Path | None = None
        self._attachments = AttachmentStore()
        self._identity_index: SessionIdentityIndex | None = None
        self.user_map: dict[str, str] = {}
        if session_manager is not None:
            self._bind_session_manager(session_manager)
        self._trace_actor_name_cache: str | None = None
        self._groups = {group.group_id: group for group in groups or []}
        self._group_filter = group_filter or DefaultGroupFilter(bot_uin)
        self._http_requester = http_requester
        self._event_bus = event_bus
        self._outbound_bound = False
        self._events_bound = False
        self._push_tool = None
        self._intake = ChannelIntake(self._accept_inbound, self.send)
        self._event_bindings = (
            EventBinding(TurnStarted, self._on_turn_started),
            EventBinding(ToolCallStarted, self._on_tool_call_started),
            EventBinding(ToolCallCompleted, self._on_tool_call_completed),
        )
        self._handlers_bound = False
        self._trace_states: dict[str, _QQTraceState] = {}
        self._bot = None
        self._sdk_runtime: QQSdkRuntime | None = None
        self._api = None
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._bot_loop: asyncio.AbstractEventLoop | None = None

    @property
    def configuration_key(self) -> tuple[str, str, float, str, str]:
        """Reuses the NcatBot connection across generations while settings hold."""
        return (
            "napcat-qq",
            self._bot_uin,
            self._websocket_open_timeout_seconds,
            self._ws_uri,
            self._ws_token,
        )

    def _bind_session_manager(self, session_manager: SessionManager) -> None:
        """Binds workspace-backed state: uploads, SELF.md, user index, fallback hub."""
        self._session_manager = session_manager
        workspace = getattr(session_manager, "workspace", None)
        self._workspace = Path(workspace) if workspace else None
        self._attachments = AttachmentStore(
            Path(workspace) / "uploads" if workspace else None
        )
        if self._channel_hub is None and workspace:
            self._channel_hub = ChannelHub.from_workspace(
                Path(workspace), session_manager=session_manager
            )
        self._identity_index = SessionIdentityIndex(
            session_manager, channel=CHANNEL, metadata_key="user_id"
        )
        self.user_map = self._identity_index.mapping

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise RuntimeError("QQChannel 尚未启动")
        return self._bus

    def _require_session_manager(self) -> SessionManager:
        if self._session_manager is None:
            raise RuntimeError("QQChannel 尚未绑定会话")
        return self._session_manager

    def _require_identity_index(self) -> SessionIdentityIndex:
        if self._identity_index is None:
            raise RuntimeError("QQChannel 尚未绑定会话")
        return self._identity_index

    def _require_http_requester(self) -> HttpRequester:
        if self._http_requester is None:
            self._http_requester = get_default_http_requester("external_default")
        return self._http_requester

    def _configure_sdk(self) -> None:
        # NcatBot configuration is process-global and may only change at activation.
        from ncatbot.utils import ncatbot_config

        patch_ncatbot_ws_open_timeout(self._websocket_open_timeout_seconds)
        # 每次激活都显式写入（含恢复默认值），避免上一代的地址/令牌残留在
        # 进程级配置里（#363 风险 3）。
        apply_napcat_connection(
            ncatbot_config.napcat, ws_uri=self._ws_uri, ws_token=self._ws_token
        )
        ncatbot_config.bt_uin = self._bot_uin
        # root 是 NcatBot 自带插件体系的管理员；Shiori 不加载 NcatBot 插件，
        # 谁能和角色说话只由角色绑定决定，这里固定为机器人自己。
        ncatbot_config.root = self._bot_uin
        ncatbot_config.check_ncatbot_update = False
        ncatbot_config.skip_ncatbot_install_check = True
        ncatbot_config.napcat.remote_mode = True
        ncatbot_config.napcat.enable_webui = False
        ncatbot_config.enable_webui_interaction = False
        ncatbot_dir = resolve_ncatbot_dir()
        ncatbot_dir.mkdir(parents=True, exist_ok=True)
        (ncatbot_dir / "plugins").mkdir(exist_ok=True)
        ncatbot_config.plugin.plugins_dir = str(ncatbot_dir / "plugins")

    async def start(self, ctx: ChannelContext | None = None) -> None:
        from ncatbot.core import BotClient

        # BotClient construction mutates SDK globals, so it belongs to activation.
        if self._bot is None:
            self._bot = BotClient()
            self._sdk_runtime = QQSdkRuntime(self._bot)
        self._intake.start(paused=ctx.intake_paused if ctx is not None else False)
        if ctx is not None:
            self._bus = ctx.bus
            self._event_bus = ctx.event_bus
            self._interrupt_controller = ctx.interrupt_controller
            self._push_tool = ctx.push_tool
            if self._http_requester is None:
                self._http_requester = ctx.http_resources.external_default
            if ctx.channel_hub is not None:
                self._channel_hub = ctx.channel_hub
            if self._session_manager is not ctx.session_manager:
                self._bind_session_manager(ctx.session_manager)
            ctx.push_tool.register_channel(
                self.name,
                text=self.send,
                file=self.send_file,
                image=self.send_image,
                description=PUSH_TARGET_HINT,
            )
        self._main_loop = asyncio.get_running_loop()
        self._configure_sdk()
        self._require_identity_index().rebuild()
        self._bind_events()
        self._bind_bot_handlers()

        logger.info("[qq] 正在启动 NcatBot（首次运行需要扫码登录）...")
        self._api = await self._main_loop.run_in_executor(None, self._bot.run_backend)
        logger.info("[qq] NcatBot 已启动")
        if not self._outbound_bound:
            self._require_bus().subscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = True

    def _bind_bot_handlers(self) -> None:
        if self._handlers_bound:
            return
        self._handlers_bound = True

        @cast(Any, self._bot.on_private_message())
        async def _(event) -> None:
            if self._bot_loop is None:
                self._bot_loop = asyncio.get_running_loop()
            user_id = str(event.user_id)
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

    def _bind_events(self) -> None:
        if self._event_bus is None or self._events_bound:
            return
        for binding in self._event_bindings:
            binding.bind(self._event_bus)
        self._events_bound = True

    async def stop(self) -> None:
        """Stops the SDK and detaches callbacks before connection replacement."""
        try:
            await self._intake.close()
            if self._sdk_runtime is not None:
                await self._sdk_runtime.stop()
                self._sdk_runtime = None
                self._bot = None
                self._handlers_bound = False
            self._api = None
            self._bot_loop = None
            logger.info("[qq] QQChannel 已停止")
        finally:
            if self._outbound_bound:
                self._require_bus().unsubscribe_outbound(CHANNEL, self._on_response)
                self._outbound_bound = False
            if self._event_bus is not None and self._events_bound:
                for binding in self._event_bindings:
                    binding.unbind(self._event_bus)
                self._events_bound = False
            if self._push_tool is not None:
                self._push_tool.unregister_channel(self.name, text=self.send)

    def pause_intake(self) -> None:
        """Buffers incoming turns while retaining the outbound SDK connection."""
        self._intake.pause()

    def resume_intake(self) -> None:
        """Restores intake after a rejected channel removal."""
        self._intake.resume()
