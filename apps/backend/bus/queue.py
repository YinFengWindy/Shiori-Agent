import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable

from bus.events import InboundItem, OutboundMessage
from bus.errors import NonRetryableDeliveryError

logger = logging.getLogger(__name__)


class MessageBus:
    """agent 与各 channel 之间的异步消息总线"""

    def __init__(self, *, outbound_retry_delay_s: float = 2.0) -> None:
        """``outbound_retry_delay_s``：出站首次可重试失败后的退避秒数。"""
        self.outbound_retry_delay_s = outbound_retry_delay_s
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
        """后台任务：按 channel 分道，将出站消息分发给对应 channel 的订阅者。

        同一 channel 的消息严格按入队顺序逐条投递；不同 channel 各自推进，
        某个 channel 在重试退避时不会阻塞其他 channel。
        """
        self._running = True
        lanes: dict[str, tuple[deque[OutboundMessage], asyncio.Task[None]]] = {}
        getter: asyncio.Task[OutboundMessage] | None = None
        try:
            while self._running:
                if getter is None:
                    getter = asyncio.create_task(self._outbound.get())
                active = {task for _, task in lanes.values() if not task.done()}
                # 同时等待取新消息与各 lane：lane 的意外异常立即从这里冒泡，
                # 与原先串行分发时一样失败即停；超时只为定期检查 stop()。
                done, _ = await asyncio.wait(
                    {getter, *active},
                    timeout=1.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if getter in done:
                    self._route_to_lane(lanes, getter.result())
                    getter = None
                for task in done & active:
                    task.result()
            # stop() 只停止取新消息，已分到各 channel 的消息照常投递完。
            await asyncio.gather(*(task for _, task in lanes.values()))
        finally:
            pending: list[asyncio.Task[object]] = [
                task for _, task in lanes.values() if not task.done()
            ]
            if getter is not None:
                pending.append(getter)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    def _route_to_lane(
        self,
        lanes: dict[str, tuple[deque[OutboundMessage], asyncio.Task[None]]],
        msg: OutboundMessage,
    ) -> None:
        lane = lanes.get(msg.channel)
        if lane is not None and not lane[1].done():
            lane[0].append(msg)
            return
        backlog: deque[OutboundMessage] = deque([msg])
        task = asyncio.create_task(
            self._drain_lane(backlog), name=f"bus_outbound_lane:{msg.channel}"
        )
        lanes[msg.channel] = (backlog, task)

    async def _drain_lane(self, backlog: deque[OutboundMessage]) -> None:
        # backlog 取空后同一步内直接结束，dispatch_outbound 看到 done 会新建 lane，
        # 两者之间没有 await，不会出现消息落进已结束 lane 的竞态。
        while backlog:
            msg = backlog.popleft()
            key = self._outbound_key(msg)
            try:
                await self._dispatch_message(msg)
            finally:
                remaining = self._pending_outbound[key] - 1
                if remaining:
                    self._pending_outbound[key] = remaining
                else:
                    self._pending_outbound.pop(key)
                self._outbound.task_done()

    async def _dispatch_message(self, msg: OutboundMessage) -> None:
        """投递一条消息：可重试的失败退避后重试一次，仍失败则发送降级通知。

        每次调用订阅者都持有 transport_lock，保证不会与连接切换/停止交错；
        退避等待期间释放锁，让其他 channel 与主动推送照常发送。
        渠道明确禁止重试时仅记录错误，避免重复发送已被接收的消息。
        """
        async with self.transport_lock:
            callbacks = tuple(self._subscribers.get(msg.channel, []))
            failed = [cb for cb in callbacks if not await self._first_attempt(cb, msg)]
        if not failed:
            return
        await asyncio.sleep(self.outbound_retry_delay_s)
        async with self.transport_lock:
            for cb in self._retry_targets(msg.channel, callbacks, failed):
                await self._retry_attempt(cb, msg)

    def _retry_targets(
        self,
        channel: str,
        attempted: tuple[Callable[[OutboundMessage], Awaitable[None]], ...],
        failed: list[Callable[[OutboundMessage], Awaitable[None]]],
    ) -> list[Callable[[OutboundMessage], Awaitable[None]]]:
        # 退避期间连接可能已被切换：仍在订阅的失败回调原样重试；
        # 已被替换掉的则改投新订阅的连接，与切换前缓冲消息走新连接的语义一致。
        current = tuple(self._subscribers.get(channel, []))
        targets = [cb for cb in failed if cb in current]
        if len(targets) < len(failed):
            targets.extend(cb for cb in current if cb not in attempted)
        return targets

    async def _first_attempt(
        self, cb: Callable[[OutboundMessage], Awaitable[None]], msg: OutboundMessage
    ) -> bool:
        """首次投递；返回 False 表示失败且允许重试。"""
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
                "分发消息到 %s 首次失败，%ss 后重试: %s",
                msg.channel,
                self.outbound_retry_delay_s,
                first_err,
            )
            return False
        return True

    async def _retry_attempt(
        self, cb: Callable[[OutboundMessage], Awaitable[None]], msg: OutboundMessage
    ) -> None:
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
