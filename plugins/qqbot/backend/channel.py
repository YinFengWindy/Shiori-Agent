"""Official QQBot channel composition and lifecycle."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable
from shiori_sdk.accounts import ConnectionState

import websockets

from shiori_sdk.channels.services import InterruptController
from shiori_sdk.channel_events import StreamDeltaReady, TurnCancelled, TurnStarted
from shiori_sdk.channels.services import MessageBus
from shiori_sdk.channels.services import ChannelHub
from shiori_sdk.channels.chat_types import ChatTypeDeclaration
from shiori_sdk.channels import ChannelContext
from shiori_sdk.channels.services import ChannelIntake

from .formatting import CHANNEL, PUSH_TARGET_HINT, SYSTEM_PROMPT_HINT
from .gateway import _GatewayMixin, _TokenCache
from .inbound import _InboundMixin
from .outbound import _OutboundMixin
from .stream_delivery import _LiveTurnKey, _StreamState
from .streaming import _StreamingMixin

logger = logging.getLogger(__name__)


class QQBotChannel(
    _GatewayMixin,
    _InboundMixin,
    _StreamingMixin,
    _OutboundMixin,
):
    """Connects the official QQBot C2C API to the shared message bus."""

    name = CHANNEL

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        chat_types: tuple[ChatTypeDeclaration, ...] = (),
        *,
        account_id: str = "",
        on_status: Callable[[ConnectionState, str, str, str], None] | None = None,
        on_target: Callable[[str], None] | None = None,
        via_account: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._app_id = app_id
        # The manifest's session types, for answering ``/chatid``.
        self._chat_types = chat_types
        self._client_secret = client_secret
        self._account_id = account_id
        self._on_status = on_status
        self._on_target = on_target
        # The application account's current message snapshot; None when the
        # channel runs without a host account.
        self._via_account = via_account
        self._public_hooks = False
        self._bus: MessageBus | None = None
        self._interrupt_controller: InterruptController | None = None
        self._channel_hub: ChannelHub | None = None
        # Opened by start(); constructing a channel must not build TLS state.
        self._client = None
        self._websocket_connect = websockets.connect
        self._token: _TokenCache | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._ready = asyncio.Event()
        self._first_gateway_result: tuple[str, str] = ("", "")
        self._connection_state = "unknown"
        self._intake: ChannelIntake | None = None
        self._event_bus = None
        self._push_tool = None
        self._event_bindings = [
            (TurnStarted, self._on_turn_started),
            (StreamDeltaReady, self._on_stream_delta),
            (TurnCancelled, self._on_turn_cancelled),
        ]
        self._outbound_bound = False
        self._events_bound = False
        self._last_c2c_msg_id: dict[str, str] = {}
        self._live_states: dict[_LiveTurnKey, _StreamState] = {}
        self._reply_buffers: dict[_LiveTurnKey, str] = {}
        self._live_next_at: dict[_LiveTurnKey, float] = {}
        self._live_stop_events: dict[_LiveTurnKey, asyncio.Event] = {}
        self._live_locks: dict[_LiveTurnKey, asyncio.Lock] = {}
        self._live_tasks: set[asyncio.Task[None]] = set()
        self._live_tasks_by_turn: dict[_LiveTurnKey, set[asyncio.Task[None]]] = {}

    @property
    def configuration_key(self):
        """Identifies independently owned connections reusable across plugin versions."""
        return (
            "official-qqbot",
            self._app_id,
            self._client_secret,
        )

    def supports_stream_events(self, chat_id: str) -> bool:
        """Streams live previews into C2C chats; groups only get final replies."""
        try:
            kind, _target = self._parse_chat_id(chat_id)
        except ValueError:
            return False
        return kind == "c2c"

    def system_prompt_hint(self, chat_id: str) -> str:
        """Keeps proactive sends on `qqbot` instead of NapCat's `qq`."""
        return SYSTEM_PROMPT_HINT

    async def start(self, ctx: ChannelContext, *, public_hooks: bool = True) -> None:
        """Registers runtime hooks and starts the official Gateway loop."""
        self._bus = ctx.bus
        self._interrupt_controller = ctx.interrupt_controller
        self._channel_hub = ctx.channel_hub
        self._event_bus = ctx.event_bus
        self._push_tool = ctx.push_tool
        self._intake = ctx.intake_factory(self._accept_inbound, self.send)
        self._open_http_client()
        self._public_hooks = public_hooks
        if public_hooks and not self._events_bound:
            for event_type, handler in self._event_bindings:
                ctx.event_bus.on(event_type, handler)
            self._events_bound = True
        if public_hooks:
            ctx.push_tool.register_channel(
                self.name,
                text=self.send_proactive,
                stream_text=self.send_stream,
                image=self.send_image,
                description=PUSH_TARGET_HINT,
            )
        self._stopped.clear()
        self._intake.start(paused=ctx.intake_paused)
        self._task = asyncio.create_task(self._gateway_loop(), name="qqbot_gateway")
        if public_hooks and not self._outbound_bound:
            ctx.bus.subscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = True
        logger.info("[qqbot] 官方 QQBot 通道已启动")

    async def stop(self) -> None:
        """Stops Gateway tasks, pending stream updates, and the HTTP client."""
        self.pause_intake()
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for session_key in list(self._live_tasks_by_turn):
            await self._finish_live_tasks(session_key)
        if self._intake is not None:
            await self._intake.close()
        await self._close_http_client()
        if self._bus is not None and self._outbound_bound:
            self._bus.unsubscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = False
        if self._event_bus is not None and self._events_bound:
            for event_type, handler in self._event_bindings:
                self._event_bus.off(event_type, handler)
            self._events_bound = False
        if self._push_tool is not None and self._public_hooks:
            self._push_tool.unregister_channel(self.name, text=self.send_proactive)
        logger.info("[qqbot] 官方 QQBot 通道已停止")

    def pause_intake(self) -> None:
        """Buffers incoming turns while existing replies remain deliverable."""
        if self._intake is not None:
            self._intake.pause()

    def resume_intake(self) -> None:
        """Restores intake after a rejected settings transaction."""
        if self._intake is not None:
            self._intake.resume()

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise RuntimeError("QQBotChannel 尚未启动")
        return self._bus

    def _chat_id(self, openid: str) -> str:
        """Chat IDs name the application, so each account's sessions stay apart."""
        return f"c2c:{self._app_id}:{openid}"

    def _parse_chat_id(self, chat_id: str) -> tuple[str, str]:
        kind, target = self._split_chat_id(chat_id)
        prefix = f"{self._app_id}:"
        if not target.startswith(prefix):
            raise ValueError("QQBot 目标不属于此应用账号")
        return kind, target[len(prefix) :]
