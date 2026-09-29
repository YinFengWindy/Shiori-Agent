"""Markdown memory 的共享请求、结果与内部契约。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from session.manager.consolidation import ConsolidationCommitRequest

if TYPE_CHECKING:
    from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate


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
    # 群环境层（#497）：整理外部段的产出写到这里；外部段非空却没有绑定时整理失败。
    group_environment: "GroupEnvironment | None" = None


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
class ConsolidationSegments:
    """一个整理窗口按发送者拆成的两段，各自保持原有顺序。

    ``user_messages`` 属于用户本人（见 ``conversation.context_scope.belongs_to_user``），
    走用户层整理；``external_messages`` 是群友、陌生人的发言以及角色在外部会话里的
    回复，按会话整理成群环境层（#497），不交给记忆引擎。游标仍按整个窗口推进。
    """

    user_messages: list[dict]
    external_messages: list[dict]


@dataclass(frozen=True)
class _ConsolidationDraft:
    window: _ConsolidationWindow
    segments: ConsolidationSegments
    source_ref: str
    history_entry_payloads: list[tuple[str, int]]
    pending_items: str
    conversation: str
    recent_context_text: str
    scope_channel: str
    scope_chat_id: str
    archive_all: bool = False
    # 外部段整理出的各会话群环境层更新，提交时由宿主写入，不发给引擎。
    group_environment_updates: tuple["GroupEnvironmentUpdate", ...] = ()


@dataclass(frozen=True)
class _ConsolidationFailure:
    step: str
    error: str
    elapsed_ms: int = 0
