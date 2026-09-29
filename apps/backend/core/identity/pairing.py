"""One-time pairing codes that bind the user's platform identity."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock

PAIRING_CODE_TTL = timedelta(minutes=10)
# Uppercase letters and digits without look-alikes (0/O, 1/I/L).
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_LENGTH = 8


@dataclass(frozen=True)
class PairingCode:
    """A code the user sends from their platform account, valid until ``expires_at``."""

    code: str
    expires_at: datetime


class PairingCodes:
    """Holds the one pending pairing code in memory.

    Creating a code replaces the previous one; a restart drops it. A code is
    consumed by its first matching use, and an expired code matches nothing.
    """

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self._clock = clock
        self._lock = RLock()
        self._pending: PairingCode | None = None

    def create(self) -> PairingCode:
        """Issues a fresh code, invalidating any earlier one."""
        code = "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
        pending = PairingCode(code, self._clock() + PAIRING_CODE_TTL)
        with self._lock:
            self._pending = pending
        return pending

    def consume(self, text: str) -> bool:
        """Uses up the pending code when ``text`` is exactly it and still valid.

        Surrounding whitespace and letter case are ignored.
        """
        candidate = text.strip().upper()
        with self._lock:
            pending = self._pending
            if pending is None or self._clock() >= pending.expires_at:
                self._pending = None
                return False
            if not secrets.compare_digest(
                candidate.encode("utf-8"), pending.code.encode("utf-8")
            ):
                return False
            self._pending = None
            return True
