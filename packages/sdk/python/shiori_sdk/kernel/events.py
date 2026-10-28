"""Typed events: ordered rewriting ``on`` chain, core checks, serial read-only ``watch``."""

from __future__ import annotations

import asyncio
import functools
import itertools
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .contracts import Veto, failure_policy, plugin_logger
from .scope import Scope

type OnHandler[E] = Callable[[E], Awaitable[E | Veto]]
type WatchHandler[E] = Callable[[E], Awaitable[None]]
type Check[E] = Callable[[E], Awaitable[E | Veto]]

WATCH_LIMIT = 256
"""Queued deliveries per (plugin, event type) before new ones are dropped (§8.3)."""


@dataclass(eq=False)
class _Subscription:
    plugin_id: str
    scope: Scope
    handler: Callable[[Any], Awaitable[Any]]
    seq: int


class _Queue(deque[tuple[Callable[[Any], Awaitable[Any]], object]]):
    worker: asyncio.Task[None] | None = None
    dropped = 0


def _require_payload(event_type: type, event: object = None) -> None:
    """Events are frozen dataclasses whose top-level fields hold no list/dict/set.

    Frozen is shallow, so a mutable container would let one handler or
    watcher change what the next one sees (§8.3). ``event`` None checks the
    type alone (``watch`` registration).
    """
    if not getattr(getattr(event_type, "__dataclass_params__", None), "frozen", False):
        raise TypeError(f"事件须为 frozen dataclass: {event_type}")
    names = getattr(event_type, "__dataclass_fields__") if event is not None else ()
    if any(isinstance(getattr(event, name), (list, dict, set)) for name in names):
        raise TypeError(f"事件的容器字段须为 tuple/只读 mapping: {event!r}")


class EventHub:
    """Dispatches events by plugin rank (dependency depth, then id), never by time.

    ``rank`` is consulted on every emit, so a plugin reloaded within the same
    plan keeps the position it had on a cold start.
    """

    def __init__(self, rank: Callable[[str], int], limit: int = WATCH_LIMIT) -> None:
        self._rank, self._limit = rank, limit
        self._seq = itertools.count()
        self._on: dict[type, list[_Subscription]] = {}
        self._watch: dict[type, list[_Subscription]] = {}
        self._checks: dict[type, list[Check[Any]]] = {}
        self._queues: dict[tuple[str, type], _Queue] = {}

    def on[E](
        self, plugin_id: str, scope: Scope, event_type: type[E], handler: OnHandler[E]
    ) -> None:
        """Adds ``handler`` to the rewriting chain of ``event_type``."""
        self._subscribe(self._on, plugin_id, scope, event_type, handler)

    def watch[E](
        self,
        plugin_id: str,
        scope: Scope,
        event_type: type[E],
        handler: WatchHandler[E],
    ) -> None:
        """Adds a read-only listener; only frozen dataclass events can be watched."""
        _require_payload(event_type)
        self._subscribe(self._watch, plugin_id, scope, event_type, handler)
        key = (plugin_id, event_type)
        _ = self._queues.setdefault(key, _Queue())
        scope.subscribe(functools.partial(self._queues.pop, key, None), "watch-queue")

    def check[E](self, event_type: type[E], check: Check[E]) -> None:
        """Adds a core check that runs on the final event after the ``on`` chain (R1)."""
        self._checks.setdefault(event_type, []).append(check)

    def _subscribe(
        self,
        table: dict[type, list[_Subscription]],
        plugin_id: str,
        scope: Scope,
        event_type: type,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> None:
        label = f"event:{event_type.__name__}"
        scope.ensure_active(label)
        subscription = _Subscription(plugin_id, scope, handler, next(self._seq))
        subscriptions = table.setdefault(event_type, [])
        subscriptions.append(subscription)
        scope.subscribe(lambda: subscriptions.remove(subscription), label)

    def _ordered(self, table: dict[type, list[_Subscription]], event_type: type):
        return sorted(
            table.get(event_type, ()),
            key=lambda sub: (self._rank(sub.plugin_id), sub.seq),
        )

    async def emit[E](self, event: E) -> E | Veto:
        """Checks the payload, runs ``on`` handlers, then core checks, then watchers.

        A handler returns the same event type (replacement) or ``Veto``;
        anything else, or a replacement breaking the payload rule, counts as
        its error. Errors follow the event type's
        ``on_error`` policy. A vetoed event reaches neither checks nor watchers.
        """
        event_type = type(event)
        _require_payload(event_type, event)
        for sub in self._ordered(self._on, event_type):
            if not sub.scope.active:
                continue
            try:
                with sub.scope.busy():
                    result = await sub.handler(event)
                if isinstance(result, Veto):
                    return result
                if type(result) is not event_type:
                    raise TypeError(f"on 处理器须返回 {event_type} 或 Veto: {result!r}")
                _require_payload(event_type, result)
                event = result
            except Exception as error:
                problem = f"插件 {sub.plugin_id} 处理 {event_type.__name__} 失败"
                plugin_logger(sub.plugin_id).exception(problem)
                if failure_policy(event_type) == "fail_closed":
                    return Veto(f"{problem}: {error}")
        for check in self._checks.get(event_type, ()):
            result = await check(event)
            if isinstance(result, Veto):
                return result
            event = result
        for sub in self._ordered(self._watch, event_type):
            if sub.scope.active:
                self._enqueue(sub, event)
        return event

    def _enqueue(self, sub: _Subscription, event: object) -> None:
        queue = self._queues[(sub.plugin_id, type(event))]
        if len(queue) >= self._limit:
            queue.dropped += 1
            message = "插件 %s 的 %s 监听队列已满，丢弃一条（累计 %d）"
            log = plugin_logger(sub.plugin_id)
            log.warning(message, sub.plugin_id, type(event), queue.dropped)
            return
        queue.append((sub.handler, event))
        if queue.worker is None or queue.worker.done():
            delivery = self._deliver(sub.plugin_id, sub.scope, queue)
            queue.worker = sub.scope.spawn(delivery, worker=True)

    async def _deliver(self, plugin_id: str, scope: Scope, queue: _Queue) -> None:
        while queue:
            handler, event = queue.popleft()
            try:
                with scope.busy():
                    await handler(event)
            except Exception:
                message = "插件 %s 监听 %s 失败"
                plugin_logger(plugin_id).exception(message, plugin_id, type(event))
