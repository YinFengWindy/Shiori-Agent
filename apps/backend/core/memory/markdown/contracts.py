"""Markdown memory 的共享请求、结果与内部契约。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from session.manager.consolidation import ConsolidationCommitRequest


@dataclass(frozen=True)
class ConsolidateRequest:
    session: object
    archive_all: bool = False
    force: bool = False
    current_content: str = ""


@dataclass
class ConsolidateResult:
    consolidated_count: int = 0
    trace: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RefreshRecentTurnsRequest:
    session: object


@dataclass(frozen=True)
class MemoryLifecycleBindRequest:
    """Bind maintenance to the session owner's validated memory commit operation."""

    get_session: Callable[[str], object]
    commit_consolidation: Callable[
        [
            ConsolidationCommitRequest,
            Callable[[], Awaitable[None]],
            Callable[[], Awaitable[None]],
        ],
        Awaitable[bool],
    ]
    after_consolidation: Callable[[object], Awaitable[None]] | None = None


@runtime_checkable
class MemoryProfileApi(Protocol):
    def read_long_term(self) -> str: ...

    def write_long_term(self, content: str) -> None: ...

    def read_self(self) -> str: ...

    def write_self(self, content: str) -> None: ...

    def read_recent_history(self, *, max_chars: int = 0) -> str: ...

    def read_recent_context(self) -> str: ...

    def write_recent_context(self, content: str) -> None: ...

    def backup_long_term(self, backup_name: str = "MEMORY.bak.md") -> None: ...

    def get_memory_context(self) -> str: ...

    def has_long_term_memory(self) -> bool: ...


@dataclass(frozen=True)
class _ConsolidationWindow:
    old_messages: list[dict]
    keep_count: int
    consolidate_up_to: int


@dataclass(frozen=True)
class _ConsolidationDraft:
    window: _ConsolidationWindow
    source_ref: str
    history_entry_payloads: list[tuple[str, int]]
    pending_items: str
    conversation: str
    recent_context_text: str
    scope_channel: str
    scope_chat_id: str
    archive_all: bool = False


@dataclass(frozen=True)
class _ConsolidationFailure:
    step: str
    error: str
    elapsed_ms: int = 0
