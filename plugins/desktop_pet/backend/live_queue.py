"""Bounded in-memory danmaku queue: arrival order, expiry and eviction.

Nothing here is persisted: a danmaku that is dropped, expired or still queued
when the run pauses or stops simply disappears.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .bilibili_danmaku import Danmaku

# How many danmaku may wait at once; older ones are evicted beyond it.
DEFAULT_QUEUE_CAPACITY = 20


@dataclass(frozen=True)
class QueuedDanmaku:
    """A danmaku and the clock time it arrived; expiry counts from arrival."""

    danmaku: Danmaku
    arrived_at: float


class DanmakuQueue:
    """Oldest-first queue that never holds more than ``capacity`` items."""

    def __init__(self, capacity: int = DEFAULT_QUEUE_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("弹幕队列容量必须为正")
        self._capacity = capacity
        self._items: deque[QueuedDanmaku] = deque()

    def __len__(self) -> int:
        return len(self._items)

    def push(self, item: QueuedDanmaku) -> int:
        """Append a new arrival; returns how many old items were evicted."""
        self._items.append(item)
        return self._trim()

    def push_front(self, item: QueuedDanmaku) -> int:
        """Return an item taken by ``pop`` to the head (the role was busy).

        It is the oldest item, so when arrivals filled the queue meanwhile it
        is the one evicted; returns how many items were evicted.
        """
        if len(self._items) >= self._capacity:
            return 1
        self._items.appendleft(item)
        return 0

    def pop(self) -> QueuedDanmaku | None:
        """Take the oldest item, if any."""
        return self._items.popleft() if self._items else None

    def drop_expired(self, now: float, wait_timeout: float) -> int:
        """Drop items that waited longer than ``wait_timeout``; returns the count."""
        dropped = 0
        while self._items and now - self._items[0].arrived_at >= wait_timeout:
            self._items.popleft()
            dropped += 1
        return dropped

    def next_expiry(self, wait_timeout: float) -> float | None:
        """Clock time at which the oldest item expires, if any is queued."""
        return self._items[0].arrived_at + wait_timeout if self._items else None

    def clear(self) -> None:
        """Forget every queued item."""
        self._items.clear()

    def _trim(self) -> int:
        evicted = 0
        while len(self._items) > self._capacity:
            self._items.popleft()
            evicted += 1
        return evicted
