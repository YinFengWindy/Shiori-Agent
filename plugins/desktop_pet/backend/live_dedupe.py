"""Per-run memory of delivered danmaku ids, to drop repeats and replays."""

from __future__ import annotations

from collections import OrderedDict

# Replays after a reconnect only repeat recent messages, so a few thousand ids
# cover any realistic gap while keeping a long run's memory bounded.
DEFAULT_SEEN_LIMIT = 5000


class SeenMessages:
    """Remembers the most recent message ids; only ids, never content."""

    def __init__(self, limit: int = DEFAULT_SEEN_LIMIT) -> None:
        self._limit = limit
        self._ids: OrderedDict[str, None] = OrderedDict()

    def first_sight(self, message_id: str) -> bool:
        """Record ``message_id``; ``False`` when it was already delivered."""
        if message_id in self._ids:
            return False
        self._ids[message_id] = None
        if len(self._ids) > self._limit:
            self._ids.popitem(last=False)
        return True
