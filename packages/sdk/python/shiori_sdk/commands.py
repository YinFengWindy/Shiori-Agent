"""Before-turn command observations and host-owned abort contract."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from .lifecycle import LifecycleFrame


@dataclass(frozen=True)
class CommandInput:
    """Current command and session memory progress, independent of model compaction."""

    content: str
    session_key: str
    messages: tuple[Mapping[str, object], ...] = ()
    last_consolidated: int = 0
    has_session: bool = True


@runtime_checkable
class CommandFrame(LifecycleFrame, Protocol):
    """A before-turn frame that can ask its host to create the normal abort result."""

    @property
    def command(self) -> CommandInput: ...
    def abort_command(self, reply: str) -> None: ...


def normalize_command(content: str) -> str:
    """Return the lowercase command head without a bot suffix or arguments."""
    parts = content.strip().split(maxsplit=1)
    return parts[0].lower().split("@", 1)[0] if parts else ""
