"""Bounded, time-limited duplicate detection for redelivered Feishu events."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable

# Feishu redelivers an unacknowledged event after 15 s, 5 min, 1 h and 6 h, so
# a key must be remembered for a bit longer than the last retry.
DEFAULT_TTL_S = 7 * 3600.0
DEFAULT_MAX_SIZE = 4096


class ExpiringIdSet:
    """Remembers ids for ``ttl`` seconds, keeping at most ``max_size`` of them.

    Thread-safe: the long-connection thread records ids while the event loop
    thread may read them.
    """

    def __init__(
        self,
        *,
        ttl: float = DEFAULT_TTL_S,
        max_size: int = DEFAULT_MAX_SIZE,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._max_size = max(1, max_size)
        self._clock = clock
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def seen(self, *keys: str) -> bool:
        """Records every nonempty key; returns whether any was already known."""
        now = self._clock()
        with self._lock:
            self._evict(now)
            duplicate = False
            for key in keys:
                if not key:
                    continue
                if key in self._seen:
                    duplicate = True
                    continue
                self._seen[key] = now + self._ttl
            while len(self._seen) > self._max_size:
                self._seen.popitem(last=False)
            return duplicate

    def __len__(self) -> int:
        with self._lock:
            self._evict(self._clock())
            return len(self._seen)

    def _evict(self, now: float) -> None:
        while self._seen:
            key, expires_at = next(iter(self._seen.items()))
            if expires_at > now:
                return
            del self._seen[key]
