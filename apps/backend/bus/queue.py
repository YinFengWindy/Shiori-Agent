import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from bus.events import InboundItem, OutboundMessage
from bus.errors import NonRetryableDeliveryError

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class _Lane:
    """单个 channel 的出站积压，以及串行投递它的任务。"""

    backlog: deque[OutboundMessage]
    task: asyncio.Task[None] = field(init=False)


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
        self._lanes: dict[str, _Lane] = {}
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
        任一 lane 的意外异常立即从这里冒泡（失败即停）。
        stop() 后不再从队列取新消息，已分到 lane 的消息投递完再返回；
        被取消或 lane 崩溃时，未投递的 lane 积压退回队列，仍计入 outbound_size。
        """
        self._running = True
        getter: asyncio.Task[OutboundMessage] | None = None
        try:
            while self._running:
                if getter is None:
                    getter = asyncio.create_task(self._outbound.get())
                # 超时只为定期检查 stop()。
                await asyncio.wait(
                    {getter, *(lane.task for lane in self._lanes.values())},
                    timeout=1.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # 先回收已结束的 lane 再路由，崩溃 lane 不会被新 lane 覆盖而漏检。
                self._reap_lanes()
                if getter.done():
                    self._route_to_lane(getter.result())
                    getter = None
            # 先停止取数再等 lane，保证 stop() 之后不会再有消息被取出。
            self._return_to_queue_front(await self._stop_getter(getter))
            getter = None
            while self._lanes:
                await asyncio.wait({lane.task for lane in self._lanes.values()})
                self._reap_lanes()
        finally:
            await self._abandon_lanes(await self._stop_getter(getter))

    def _reap_lanes(self) -> None:
        """移除正常结束的 lane；有 lane 意外失败时抛出其异常（失败即停）。

        失败的 lane 留在表中，由 dispatch_outbound 收尾时把积压退回队列。
        """
        finished = [
            channel
            for channel, lane in self._lanes.items()
            if lane.task.done()
            and not lane.task.cancelled()
            and lane.task.exception() is None
        ]
        for channel in finished:
            del self._lanes[channel]
        for lane in self._lanes.values():
            if lane.task.done():
                lane.task.result()

    async def _abandon_lanes(self, fetched: list[OutboundMessage]) -> None:
        """取消剩余 lane，把未投递的积压和已取出未路由的消息按原顺序退回队首。"""
        lanes = list(self._lanes.values())
        for lane in lanes:
            lane.task.cancel()
        # return_exceptions 同时取回失败 lane 的异常，避免未取回告警。
        await asyncio.gather(*(lane.task for lane in lanes), return_exceptions=True)
        self._lanes.clear()
        # 各 lane 积压都早于 getter 取出的那条，按此顺序放回即保持同 channel 次序。
        leftovers = [msg for lane in lanes for msg in lane.backlog] + fetched
        if leftovers:
            logger.warning("出站分发中止，%d 条未投递消息退回队列", len(leftovers))
        self._return_to_queue_front(leftovers)

    @staticmethod
    async def _stop_getter(
        getter: asyncio.Task[OutboundMessage] | None,
    ) -> list[OutboundMessage]:
        """取消取数任务；若它已取出消息则返回该消息，交由调用方放回。"""
        if getter is None:
            return []
        getter.cancel()
        await asyncio.gather(getter, return_exceptions=True)
        # Queue.get 在被唤醒前取消不会出队，只有真正完成时才带着消息。
        if getter.cancelled() or getter.exception() is not None:
            return []
        return [getter.result()]

    def _return_to_queue_front(self, messages: list[OutboundMessage]) -> None:
        """把已出队但未投递的消息放回队首，仍计入 outbound_size 与 join。"""
        if not messages:
            return
        rest: list[OutboundMessage] = []
        while not self._outbound.empty():
            rest.append(self._outbound.get_nowait())
        for msg in (*messages, *rest):
            # put_nowait 再记一次未完成任务，task_done 抵消原先那次，join 计数不变。
            self._outbound.put_nowait(msg)
            self._outbound.task_done()

    def _route_to_lane(self, msg: OutboundMessage) -> None:
        """把消息追加到其 channel 的 lane；该 channel 没有进行中的 lane 时新建一条。"""
        lane = self._lanes.get(msg.channel)
        if lane is not None:
            lane.backlog.append(msg)
            return
        lane = _Lane(deque([msg]))
        lane.task = asyncio.create_task(
            self._drain_lane(lane), name=f"bus_outbound_lane:{msg.channel}"
        )
        self._lanes[msg.channel] = lane

    async def _drain_lane(self, lane: "_Lane") -> None:
        # backlog 取空后同一步内直接结束；dispatch_outbound 回收后才会新建 lane，
        # 两者之间没有 await，不会出现消息落进已结束 lane 的竞态。
        # 中止时剩余 backlog 保留在 lane 上，由 dispatch_outbound 统一退回队列。
        while lane.backlog:
            msg = lane.backlog.popleft()
            try:
                await self._dispatch_message(msg)
            finally:
                self._settle(msg)

    def _settle(self, msg: OutboundMessage) -> None:
        key = self._outbound_key(msg)
        remaining = self._pending_outbound[key] - 1
        if remaining:
            self._pending_outbound[key] = remaining
        else:
            self._pending_outbound.pop(key)
        self._outbound.task_done()

    async def _dispatch_message(self, msg: OutboundMessage) -> None:
        """投递一条消息：可重试的失败退避后重试一次，仍失败则发送降级通知。

        每次调用订阅者都持有 transport_lock，保证不会与连接切换/停止交错。
        退避等待期间释放锁，让其他 channel 与主动推送照常发送；代价是同一会话里
        MessagePushTool.push 的消息可能先于这条重试的回复送达（可接受的取舍）。
        渠道明确禁止重试时仅记录错误，避免重复发送已被接收的消息。
        """
        async with self.transport_lock:
            attempted = tuple(self._subscribers.get(msg.channel, []))
            failed: list[Callable[[OutboundMessage], Awaitable[None]]] = []
            for cb in attempted:
                error = await self._deliver_once(cb, msg, retrying=False)
                if error is not None:
                    logger.warning(
                        "分发消息到 %s 首次失败，%ss 后重试: %s",
                        msg.channel,
                        self.outbound_retry_delay_s,
                        error,
                    )
                    failed.append(cb)
        if not failed:
            return
        await asyncio.sleep(self.outbound_retry_delay_s)
        async with self.transport_lock:
            for cb in self._retry_targets(msg, attempted, failed):
                error = await self._deliver_once(cb, msg, retrying=True)
                if error is not None:
                    logger.error(
                        "分发消息到 %s 重试仍失败，发送降级通知: %s", msg.channel, error
                    )
                    await self._send_failure_notice(cb, msg)

    def _retry_targets(
        self,
        msg: OutboundMessage,
        attempted: tuple[Callable[[OutboundMessage], Awaitable[None]], ...],
        failed: list[Callable[[OutboundMessage], Awaitable[None]]],
    ) -> list[Callable[[OutboundMessage], Awaitable[None]]]:
        # 退避期间连接可能已被切换。整体切换（首轮尝试过的订阅者都已移除）时，
        # 与切换前缓冲消息一致，改投当前订阅者；部分切换时只重试仍在订阅的失败回调，
        # 已移除的失败回调无法对应到替代者，记错误而不是静默丢弃或误投。
        current = tuple(self._subscribers.get(msg.channel, []))
        if not any(cb in current for cb in attempted):
            targets = list(current)
        else:
            targets = [cb for cb in failed if cb in current]
            if len(targets) < len(failed):
                logger.error(
                    "退避期间 %d 个失败的连接已被移除，放弃对其重试 "
                    "channel=%s chat_id=%s",
                    len(failed) - len(targets),
                    msg.channel,
                    msg.chat_id,
                )
        if not targets:
            logger.error(
                "重试时没有可用的连接，消息未送达 channel=%s chat_id=%s",
                msg.channel,
                msg.chat_id,
            )
        return targets

    @staticmethod
    async def _deliver_once(
        cb: Callable[[OutboundMessage], Awaitable[None]],
        msg: OutboundMessage,
        *,
        retrying: bool,
    ) -> Exception | None:
        """投递一次；仅在失败且允许重试时返回该异常，成功或渠道禁止重试时返回 None。"""
        try:
            await cb(msg)
        except NonRetryableDeliveryError as exc:
            logger.error(
                "%s，渠道禁止再次重试或替换 channel=%s chat_id=%s: %s",
                "重试分发失败" if retrying else "分发消息失败",
                msg.channel,
                msg.chat_id,
                exc,
            )
        except Exception as exc:
            return exc
        return None

    @staticmethod
    async def _send_failure_notice(
        cb: Callable[[OutboundMessage], Awaitable[None]], msg: OutboundMessage
    ) -> None:
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
        """尚未开始投递的出站消息数：队列中的加上已分到各 lane 的积压。

        dispatch_outbound 刚取出、下一步即路由的那一条不计入，这只是调度器
        存活时的瞬时状态；调度器退出时会把它放回队列。
        """
        return self._outbound.qsize() + sum(
            len(lane.backlog) for lane in self._lanes.values()
        )
