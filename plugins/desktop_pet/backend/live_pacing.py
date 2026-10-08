"""When the next live reply may be generated.

A shown reply holds the line until its output outcome arrives (or
``OUTPUT_TIMEOUT_S`` passes); then the user's reply interval runs. A busy
role is retried after a short fixed delay instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .live_clock import Clock

# Upper bound on one reply's bubble + speech before the next may start.
OUTPUT_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class _Pending:
    reply_id: str
    deadline: float


class ReplyPacer:
    """Tracks the one pending output and the earliest next generation time."""

    def __init__(self, clock: Clock, interval: Callable[[], float]) -> None:
        self._clock = clock
        self._interval = interval
        self._pending: _Pending | None = None
        self._ready_at = 0.0

    @property
    def output_pending(self) -> bool:
        """Whether a shown reply still awaits its outcome."""
        return self._pending is not None

    def awaiting(self, reply_id: str) -> None:
        """A reply was handed to the pet; hold until its outcome."""
        self._pending = _Pending(reply_id, self._clock.now() + OUTPUT_TIMEOUT_S)

    def finished(self, reply_id: str) -> bool:
        """The reply's outcome arrived; ``False`` if it was not the pending one."""
        if self._pending is None or self._pending.reply_id != reply_id:
            return False
        self._pending = None
        self.cool_down()
        return True

    def cool_down(self) -> None:
        """Start the reply interval now."""
        self._ready_at = self._clock.now() + self._interval()

    def retry_after(self, seconds: float) -> None:
        """Allow the next attempt only after ``seconds``."""
        self._ready_at = self._clock.now() + seconds

    def wait_time(self) -> tuple[float, str | None]:
        """Seconds until a reply may start (0: now), and a reply that timed out."""
        now = self._clock.now()
        lost = None
        if self._pending is not None:
            if now < self._pending.deadline:
                return self._pending.deadline - now, None
            lost = self._pending.reply_id
            self._pending = None
            self.cool_down()
        return max(self._ready_at - now, 0.0), lost
