"""Official QQBot channel composition and lifecycle."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import httpx
import websockets

from agent.looping.interrupt import InterruptController
from bus.events_lifecycle import StreamDeltaReady, TurnStarted
from bus.queue import MessageBus
from core.channels import ChannelHub
from infra.channels.contract import ChannelContext

from .formatting import CHANNEL
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
        allow_from: list[str] | None = None,
        groups: list["QQBotGroupConfigModel"] | None = None,
    ) -> None:
        self._app_id = app_id
        self._client_secret = client_secret
        self._allow_from = {
            str(value).strip() for value in (allow_from or []) if str(value).strip()
        }
        self._groups = {str(group.group_openid): group for group in (groups or [])}
        self._bus: MessageBus | None = None
        self._interrupt_controller: InterruptController | None = None
        self._channel_hub: ChannelHub | None = None
        self._client = httpx.AsyncClient(timeout=30.0)
        self._websocket_connect = websockets.connect
        self._token: _TokenCache | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._outbound_bound = False
        self._events_bound = False
        self._last_c2c_msg_id: dict[str, str] = {}
        self._live_states: dict[str, _LiveStreamState] = {}
        self._reply_buffers: dict[str, str] = {}
        self._live_next_at: dict[str, float] = {}
        self._live_last_lengths: dict[str, int] = {}
        self._live_failures: dict[str, int] = {}
        self._live_disabled: set[str] = set()
        self._live_locks: dict[str, asyncio.Lock] = {}
        self._live_tasks: set[asyncio.Task[None]] = set()
        self._live_tasks_by_session: dict[str, set[asyncio.Task[None]]] = {}

    async def start(self, ctx: ChannelContext) -> None:
        """Registers runtime hooks and starts the official Gateway loop."""
        self._bus = ctx.bus
        self._interrupt_controller = ctx.interrupt_controller
        self._channel_hub = ctx.channel_hub
        if not self._events_bound:
            ctx.event_bus.on(TurnStarted, self._on_turn_started)
            ctx.event_bus.on(StreamDeltaReady, self._on_stream_delta)
            self._events_bound = True
        ctx.push_tool.register_channel(
            self.name,
            text=self.send_proactive,
            stream_text=self.send_stream,
            image=self.send_image,
        )
        self._stopped.clear()
        self._task = asyncio.create_task(self._gateway_loop(), name="qqbot_gateway")
        if not self._outbound_bound:
            ctx.bus.subscribe_outbound(CHANNEL, self._on_response)
            self._outbound_bound = True
        logger.info("[qqbot] 官方 QQBot 通道已启动")

    async def stop(self) -> None:
        """Stops Gateway tasks, pending stream updates, and the HTTP client."""
        self._stopped.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._drain_live_tasks()
        await self._client.aclose()
        logger.info("[qqbot] 官方 QQBot 通道已停止")

    def _require_bus(self) -> MessageBus:
        if self._bus is None:
            raise RuntimeError("QQBotChannel 尚未启动")
        return self._bus


# Compatibility exports for tests and callers that imported old module helpers.
_CHANNEL = CHANNEL


def _iter_stream_chunks(text: str, limit: int = 160) -> list[str]:
    from .formatting import iter_stream_chunks

    return iter_stream_chunks(text, limit)


def _format_turn_live(reply: str) -> str:
    from .formatting import format_turn_live

    return format_turn_live(reply)


def _tail_text(text: str, limit: int) -> str:
    from .formatting import tail_text

    return tail_text(text, limit)


def _as_dict(value: object) -> dict[str, Any]:
    from .formatting import as_dict

    return as_dict(value)
