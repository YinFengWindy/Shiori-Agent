"""Markdown memory 的共享请求、结果与内部契约。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.memory.external_writes import ExternalLayerSnapshot
from session.manager.consolidation import ConsolidationCommitRequest
from session.store.common import ContextScope

if TYPE_CHECKING:
    from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
    from core.memory.member_profiles import MemberProfileUpdate
    from core.roles import RoleStore


@dataclass(frozen=True)
class ConsolidateRequest:
    session: object
    archive_all: bool = False
    force: bool = False
    current_content: str = ""
    # 角色会话只整理这类上下文（按其预算判断）；None 表示各类上下文都看一遍。
    # ``current_content`` 只计入这类上下文的预算。force 与 archive_all 总是两类一起推进。
    scope: ContextScope | None = None
    # The owning final request already exceeded its model input budget.
    input_budget_exceeded: bool = False


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
    # 群环境层（#497）：整理外部段的产出写到这里；未绑定时整理直接失败。
    group_environment: "GroupEnvironment | None" = None
    # 运行时共享的角色存储（#498）：按此刻身份绑定认出用户本人，不为其建成员档案；
    # 未绑定时整理直接失败。
    runtime_roles: "RoleStore | None" = None


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
class ConsolidationWindow:
    """一次整理要处理的消息窗口；角色会话整理与旁听整理（#541）共用。

    ``old_messages`` 是窗口里的已存消息（或同形的旁听记录），``consolidate_up_to``
    是提交后游标推进到的位置（会话消息下标；旁听整理是该批最后一条的 ``seq``）。
    """

    old_messages: list[dict]
    keep_count: int
    consolidate_up_to: int
    # 本窗口推进哪些上下文的游标（#523）；为空表示非角色会话，推进 last_consolidated。
    scopes: tuple[ContextScope, ...] = ()


@dataclass(frozen=True)
class ConsolidationSegments:
    """一个整理窗口按发送者拆成的两段，各自保持原有顺序。

    ``user_messages`` 属于用户本人（见 ``conversation.context_scope.belongs_to_user``），
    走用户层整理；``external_messages`` 是群友、陌生人的发言以及角色在外部会话里的
    回复，按会话整理成群环境层（#497）与成员层（#498），不交给记忆引擎。游标仍按整个窗口推进。
    """

    user_messages: list[dict]
    external_messages: list[dict]


@dataclass(frozen=True)
class ExternalLayerUpdates:
    """外部段一次整理的产出：各会话的群环境层更新（#497）与成员档案更新（#498）。"""

    group_environment: tuple["GroupEnvironmentUpdate", ...] = ()
    member_profiles: tuple["MemberProfileUpdate", ...] = ()
    # 准备时读到、且上面的更新会写回的群笔记与档案，提交时据此做乐观校验（#499）。
    snapshot: ExternalLayerSnapshot = field(default_factory=ExternalLayerSnapshot)


@dataclass(frozen=True)
class _ConsolidationDraft:
    window: ConsolidationWindow
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
    # 外部段整理出的成员档案更新（#498），提交时由宿主写入，不发给引擎。
    member_profile_updates: tuple["MemberProfileUpdate", ...] = ()
    # 上面两类更新会写回的群笔记与档案在准备时的内容；提交时被改过则整次按过期处理。
    external_snapshot: ExternalLayerSnapshot = field(
        default_factory=ExternalLayerSnapshot
    )


@dataclass(frozen=True)
class ConsolidationFailure:
    """整理某一步（LLM 调用等）的明确失败：本次不提交、游标不推进，下次重试。"""

    step: str
    error: str
    elapsed_ms: int = 0
