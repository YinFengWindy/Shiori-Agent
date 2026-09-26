import asyncio
import logging
from collections.abc import Awaitable, Callable

from bus.events import InboundItem, OutboundMessage
from bus.errors import NonRetryableDeliveryError

logger = logging.getLogger(__name__)


class MessageBus:
    """agent 与各 channel 之间的异步消息总线"""

    def __init__(self) -> None:
        self._inbound: asyncio.Queue[InboundItem] = asyncio.Queue()
        self._outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()
        self._pending_outbound: dict[tuple[str, str, str], int] = {}
        self._subscribers: dict[
            str, list[Callable[[OutboundMessage], Awaitable[None]]]
        ] = {}
        self._running = False
        self._accepting_inbound = True
        self._lease_factory: Callable | None = None
        self.transport_lock = asyncio.Lock()

    def bind_runtime_admission(self, lease_factory: Callable) -> None:
        """Captures the accepting runtime for queued channel messages and their replies."""
        self._lease_factory = lease_factory

    async def publish_inbound(self, msg: InboundItem) -> None:
        """channel → agent"""
        if not self._accepting_inbound:
            await self._release_inbound(msg)
            return
        if msg.runtime_lease is None and self._lease_factory is not None:
            msg.runtime_lease = self._lease_factory()
        await self._inbound.put(msg)

    async def close_inbound(self) -> None:
        """Rejects new intake and releases queued task ownership during shutdown."""
        self._accepting_inbound = False
        while not self._inbound.empty():
            await self._release_inbound(self._inbound.get_nowait())

    @staticmethod
    async def _release_inbound(item: InboundItem) -> None:
        if item.runtime_lease is not None:
            await item.runtime_lease.release()

    async def consume_inbound(self) -> InboundItem:
        """阻塞直到有消息可消费"""
        return await self._inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """agent → channel"""
        key = self._outbound_key(msg)
        self._pending_outbound[key] = self._pending_outbound.get(key, 0) + 1
        await self._outbound.put(msg)

    @staticmethod
    def _outbound_key(msg: OutboundMessage) -> tuple[str, str, str]:
        return (
            msg.channel,
            msg.chat_id,
            str(msg.metadata.get("external_message_id") or ""),
        )

    def has_pending_outbound(
        self, channel: str, chat_id: str, external_message_id: str
    ) -> bool:
        """Whether this originating message has a queued or dispatching reply."""
        return (
            self._pending_outbound.get((channel, chat_id, external_message_id), 0) > 0
        )

    def subscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], Awaitable[None]],
    ) -> None:
        """订阅某 channel 的出站消息"""
        subscribers = self._subscribers.setdefault(channel, [])
        if callback not in subscribers:
            subscribers.append(callback)

    def unsubscribe_outbound(
        self,
        channel: str,
        callback: Callable[[OutboundMessage], Awaitable[None]],
    ) -> None:
        """Removes a transport callback before replacing or stopping its connection."""
        subscribers = self._subscribers.get(channel, [])
        self._subscribers[channel] = [item for item in subscribers if item != callback]
        if not self._subscribers[channel]:
            self._subscribers.pop(channel, None)

    async def dispatch_outbound(self) -> None:
        """后台任务：将出站消息分发给对应 channel 的订阅者。

        可重试的失败退避 2s 重试一次；仍失败则发送降级错误通知。
        渠道明确禁止重试时仅记录错误，避免重复发送已被接收的消息。
        """
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self._outbound.get(), timeout=1.0)
                key = self._outbound_key(msg)
                try:
                    async with self.transport_lock:
                        await self._dispatch_message(msg)
                finally:
                    remaining = self._pending_outbound[key] - 1
                    if remaining:
                        self._pending_outbound[key] = remaining
                    else:
                        self._pending_outbound.pop(key)
                    self._outbound.task_done()
            except asyncio.TimeoutError:
                continue

    async def _dispatch_message(self, msg: OutboundMessage) -> None:
        for cb in tuple(self._subscribers.get(msg.channel, [])):
            try:
                await cb(msg)
            except NonRetryableDeliveryError as exc:
                logger.error(
                    "分发消息失败，渠道禁止重试或替换 channel=%s chat_id=%s: %s",
                    msg.channel,
                    msg.chat_id,
                    exc,
                )
            except Exception as first_err:
                logger.warning(
                    "分发消息到 %s 首次失败，2s 后重试: %s", msg.channel, first_err
                )
                await asyncio.sleep(2)
                try:
                    await cb(msg)
                except NonRetryableDeliveryError as exc:
                    logger.error(
                        "重试分发失败，渠道禁止再次重试或替换 channel=%s chat_id=%s: %s",
                        msg.channel,
                        msg.chat_id,
                        exc,
                    )
                except Exception as second_err:
                    logger.error(
                        "分发消息到 %s 重试仍失败，发送降级通知: %s",
                        msg.channel,
                        second_err,
                    )
                    fallback = OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="（消息发送失败，请稍后重试）",
                        metadata=dict(msg.metadata or {}),
                    )
                    try:
                        await cb(fallback)
                    except Exception:
                        logger.error(
                            "降级通知也失败，消息彻底丢失 channel=%s chat_id=%s",
                            msg.channel,
                            msg.chat_id,
                        )

    def stop(self) -> None:
        self._running = False

    async def drain_outbound(self) -> None:
        """Waits for queued replies before retiring their last transport."""
        await self._outbound.join()

    @property
    def inbound_size(self) -> int:
        return self._inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return self._outbound.qsize()
