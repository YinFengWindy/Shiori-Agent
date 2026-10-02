"""Telegram update replay policy, owned by the platform adapter."""

from collections import deque


class MessageDeduper:
    """滑动窗口去重，避免 channel 重投或重复事件被处理多次。"""

    def __init__(self, max_size: int) -> None:
        self._max_size = max(1, max_size)
        self._seen: set[str] = set()
        self._order: deque[str] = deque()

    def seen(self, key: str) -> bool:
        if key in self._seen:
            return True
        self._seen.add(key)
        self._order.append(key)
        while len(self._order) > self._max_size:
            self._seen.discard(self._order.popleft())
        return False
