from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from agent.prompting.assembler import PromptSectionRender
from bus.events import InboundMessage, OutboundMessage
from conversation.context_scope import source_belongs_to_user
from core.common.message_source import MessageSource
from shiori_sdk.lifecycle import (
    AfterReasoningCtx as AfterReasoningCtx,
)
from shiori_sdk.lifecycle import (
    AfterStepCtx as AfterStepCtx,
)
from shiori_sdk.lifecycle import AfterToolResultCtx as AfterToolResultCtx
from shiori_sdk.tool_hooks import PreToolCtx as PreToolCtx

if TYPE_CHECKING:
    from agent.core.runtime_support import SessionLike, TurnRunResult
    from agent.core.types import HistoryMessage
    from agent.turns.turn_pushes import TurnPushDrafts
    from conversation.context_scope import ContextScope, ContextView


# 1. 工厂函数：给 dataclass field(default_factory=...) 提供显式类型签名，消除 pyright Unknown 推断。
def _empty_str_list() -> list[str]:
    return []


def _empty_metadata() -> dict[str, Any]:
    return {}


def _empty_prompt_sections() -> list[PromptSectionRender]:
    return []


def inbound_thread_id(msg: InboundMessage) -> str:
    """入站消息所在会话（thread）；渠道中枢与桌面入口写在 metadata 里，没有时为空串。

    回合装配（可见历史、提示词渲染与预热、用户本人判定）都从这里取，保证同一来源。
    """
    return str((msg.metadata or {}).get("thread_id") or "").strip()


@dataclass
class TurnState:
    msg: InboundMessage
    session_key: str
    dispatch_outbound: bool
    session: SessionLike | None = None
    extra_metadata: dict[str, Any] = field(default_factory=_empty_metadata)
    turn_pushes: TurnPushDrafts | None = None
    committed_message_ids: tuple[str, ...] = ()
    # 角色共享会话里的回合按所在会话算出的可见历史范围；其他会话为 None，历史不筛选。
    context_view: ContextView | None = None

    @property
    def context_scope(self) -> ContextScope | None:
        """回合所在的上下文；非角色共享会话为 None。"""
        return self.context_view.scope if self.context_view is not None else None

    @property
    def thread_id(self) -> str:
        """回合所在会话（见 ``inbound_thread_id``）。"""
        return inbound_thread_id(self.msg)

    def is_user_authored(self) -> bool:
        """本回合的来信是否出自用户本人（规则见 ``source_belongs_to_user``）。

        角色共享会话混存各渠道的消息，群友与陌生人的发言不能当成用户本人的；
        其他会话只有一段对话，没有划分，照旧视为用户本人。
        """
        if self.context_view is None:
            return True
        return source_belongs_to_user(
            self.thread_id,
            MessageSource.from_inbound(self.msg),
            self.context_view.user_threads,
        )


@dataclass
class BeforeTurnCtx:
    # before-* ctx 走 GATE 链，插件可直接改写字段影响后续阶段。
    # read-only by convention
    session_key: str
    channel: str
    chat_id: str
    content: str
    timestamp: datetime
    retrieved_memory_block: str
    retrieval_trace_raw: object | None
    history_messages: tuple[HistoryMessage, ...]
    # 回合所在的上下文（用户 / 外部），取自 TurnState.context_scope；非角色共享会话为 None。
    context_scope: ContextScope | None
    # writable
    skill_names: list[str] = field(default_factory=_empty_str_list)
    abort: bool = False
    abort_reply: str = ""
    extra_hints: list[str] = field(default_factory=_empty_str_list)
    extra_metadata: dict[str, Any] = field(default_factory=_empty_metadata)


@dataclass(frozen=True)
class BeforeReasoningInput:
    state: TurnState
    before_turn: BeforeTurnCtx


@dataclass
class BeforeReasoningCtx:
    # before-* ctx 走 GATE 链，插件可直接改写字段影响后续阶段。
    # read-only by convention
    session_key: str
    channel: str
    chat_id: str
    content: str
    timestamp: datetime
    # writable
    skill_names: list[str]
    retrieved_memory_block: str
    extra_hints: list[str] = field(default_factory=_empty_str_list)
    abort: bool = False
    abort_reply: str = ""


@dataclass(frozen=True)
class PromptRenderInput:
    session_key: str
    channel: str
    chat_id: str
    content: str
    media: list[str] | None
    timestamp: datetime
    history: list[dict[str, Any]]
    skill_names: list[str] | None
    retrieved_memory_block: str
    disabled_sections: set[str]
    turn_injection_prompt: str
    extra_hints: list[str] | None = None
    message_source: MessageSource | None = None
    session_metadata: dict[str, Any] = field(default_factory=_empty_metadata)
    # 回合所在的上下文，取自 TurnState.context_scope；决定注入哪些记忆。
    context_scope: ContextScope | None = None
    # 回合所在会话（thread）；外部回合据此注入当前会话的群笔记（#497）。
    thread_id: str = ""
    # 本回合可见历史窗口里非用户本人消息的来源，旧的在前；外部回合据此注入成员档案（#498）。
    window_sources: tuple[MessageSource, ...] = ()
    # Idle context inspection has no draft/current turn; use the same owner render.
    include_current_message: bool = True


@dataclass
class PromptRenderCtx:
    # render/before-step ctx 走 GATE 链，插件可直接改写字段影响后续阶段。
    # read-only by convention
    session_key: str
    channel: str
    chat_id: str
    content: str
    media: list[str] | None
    timestamp: datetime
    history: list[dict[str, Any]]
    skill_names: list[str] | None
    retrieved_memory_block: str
    disabled_sections: set[str]
    turn_injection_prompt: str
    session_metadata: dict[str, Any] = field(default_factory=_empty_metadata)
    extra_hints: list[str] = field(default_factory=_empty_str_list)
    # writable
    system_sections_top: list[PromptSectionRender] = field(
        default_factory=_empty_prompt_sections
    )
    system_sections_bottom: list[PromptSectionRender] = field(
        default_factory=_empty_prompt_sections
    )


@dataclass(frozen=True)
class PromptRenderResult:
    messages: list[dict[str, Any]]


@dataclass(frozen=True)
class BeforeStepInput:
    session_key: str
    channel: str
    chat_id: str
    iteration: int
    messages: list[dict[str, Any]]
    visible_names: set[str] | None


@dataclass
class BeforeStepCtx:
    # before-* ctx 走 GATE 链，插件可直接改写字段影响后续阶段。
    # read-only by convention
    session_key: str
    channel: str
    chat_id: str
    iteration: int
    input_tokens_estimate: int
    visible_tool_names: frozenset[str] | None
    # writable
    extra_hints: list[str] = field(default_factory=_empty_str_list)
    early_stop: bool = False
    early_stop_reply: str = ""


@dataclass(frozen=True)
class AfterReasoningInput:
    state: TurnState
    turn_result: TurnRunResult


@dataclass(frozen=True)
class AfterReasoningResult:
    ctx: AfterReasoningCtx
    outbound: OutboundMessage


@dataclass
class TurnSnapshot:
    state: TurnState
    outbound: OutboundMessage
    ctx: AfterReasoningCtx


@dataclass(frozen=True)
class AfterTurnCtx:
    # after-* fanout ctx 是观察快照；需要补充 metadata 时由 PhaseModule replace 新实例。
    session_key: str
    channel: str
    chat_id: str
    reply: str
    tools_used: tuple[str, ...]
    thinking: str | None
    # pre-dispatch intent flag: dispatch has NOT happened yet when Tap handlers run
    will_dispatch: bool
    extra_metadata: dict[str, Any] = field(default_factory=_empty_metadata)


@dataclass(frozen=True)
class BeforeToolCallCtx:
    session_key: str
    channel: str
    chat_id: str
    tool_name: str
    arguments: dict[str, Any]
