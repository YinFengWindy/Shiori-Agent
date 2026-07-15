"""Markdown memory 的共享请求、结果与内部契约。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConsolidateRequest:
    session: object
    archive_all: bool = False
    force: bool = False


@dataclass
class ConsolidateResult:
    consolidated_count: int = 0
    trace: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RefreshRecentTurnsRequest:
    session: object


@dataclass(frozen=True)
class MemoryLifecycleBindRequest:
    get_session: Callable[[str], object]
    save_session: Callable[[object], Awaitable[None]]
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
