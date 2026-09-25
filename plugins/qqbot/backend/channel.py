"""Official QQBot channel composition and lifecycle."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx
import websockets

from agent.looping.interrupt import InterruptController
from bus.events_lifecycle import StreamDeltaReady, TurnStarted
from bus.queue import MessageBus
from core.channels import ChannelHub
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake

from .formatting import CHANNEL, PUSH_TARGET_HINT, SYSTEM_PROMPT_HINT
from .gateway import _GatewayMixin, _TokenCache
from .inbound import _InboundMixin
from .outbound import _OutboundMixin
from .streaming import _LiveStreamState, _StreamingMixin

if TYPE_CHECKING:
    from .plugin import QQBotGroupConfigModel

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
        groups: list["QQBotGroupConfigModel"] | None = None,
    ) -> None:
        self._app_id = app_id
        self._client_secret = client_secret
        self._groups = {str(group.group_openid): group for group in (groups or [])}
        self._bus: MessageBus | None = None
        self._interrupt_controller: InterruptController | None = None
        self._channel_hub: ChannelHub | None = None
        self._client = httpx.AsyncClient(timeout=30.0)
        self._websocket_connect = websockets.connect
        self._token: _TokenCache | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._intake = ChannelIntake(self._accept_inbound, self.send)
        self._event_bus = None
        self._push_tool = None
        self._event_bindings = [
            (TurnStarted, self._on_turn_started),
            (StreamDeltaReady, self._on_stream_delta),
        ]
        self._outbound_bound = False
        self._events_bound = False
        self._last_c2c_msg_id: dict[str, str] = {}
        self._live_states: dict[str, _LiveStreamState] = {}
        self._reply_buffers: dict[str, str] = {}
        self._live_next_at: dict[str, float] = {}
        self._live_failures: dict[str, int] = {}
        self._live_disabled: set[str] = set()
        self._live_locks: dict[str, asyncio.Lock] = {}
        self._live_tasks: set[asyncio.Task[None]] = set()
        self._live_tasks_by_session: dict[str, set[asyncio.Task[None]]] = {}

    @property
    def configuration_key(self):
        """Identifies independently owned connections reusable across plugin versions."""
        return (
            "official-qqbot",
            self._app_id,
            self._client_secret,
            {key: group.model_dump() for key, group in self._groups.items()},
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

    async def start(self, ctx: ChannelContext) -> None:
        """Registers runtime hooks and starts the official Gateway loop."""
        self._bus = ctx.bus
        self._interrupt_controller = ctx.interrupt_controller
        self._channel_hub = ctx.channel_hub
        self._event_bus = ctx.event_bus
        self._push_tool = ctx.push_tool
        if self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        if not self._events_bound:
            for event_type, handler in self._event_bindings:
                ctx.event_bus.on(event_type, handler)
            self._events_bound = True
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
        if not self._outbound_bound:
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
        await self._drain_live_tasks()
        await self._intake.close()
        await self._client.aclose()
        if self._bus is not None and self._outbound_bound:
            self._bus.unsubscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = False
        if self._event_bus is not None and self._events_bound:
            for event_type, handler in self._event_bindings:
                self._event_bus.off(event_type, handler)
            self._events_bound = False
        if self._push_tool is not None:
            self._push_tool.unregister_channel(self.name, text=self.send_proactive)
        logger.info("[qqbot] 官方 QQBot 通道已停止")

    def pause_intake(self) -> None:
        """Buffers incoming turns while existing replies remain deliverable."""
        self._intake.pause()

    def resume_intake(self) -> None:
        """Restores intake after a rejected settings transaction."""
        self._intake.resume()

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise RuntimeError("QQBotChannel 尚未启动")
        return self._bus
