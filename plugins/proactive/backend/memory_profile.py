"""Profile reads a proactive prompt takes from one role's markdown memory."""

from __future__ import annotations

from typing import Protocol


class MemoryProfile(Protocol):
    """Long-term memory, self text and recent context of one role."""

    def read_long_term(self) -> str: ...

    def read_self(self) -> str: ...

    def read_recent_context(self) -> str: ...
