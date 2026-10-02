"""Lifecycle values and extension protocols shared by plugins and the host."""

from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from .prompting import PromptSectionRender


class LifecycleFrame(Protocol):
    """A phase's shared slots; input and output remain owned by that phase."""

    @property
    def slots(self) -> MutableMapping[str, object]: ...


class LifecycleModule(Protocol):
    """A contribution preserves its concrete frame while updating shared slots."""

    @property
    def slot(self) -> str: ...

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT: ...


class LifecycleCapability(Protocol):
    """Registers modules for the lifetime of the plugin's granted scope."""

    def contribute(self, slot: str, modules: Sequence[LifecycleModule]) -> None: ...


@dataclass
class ResponseMetadata:
    """Formal reply fields retained separately from displayed content."""

    raw_text: str
    mood: str | None = None
    thought: str | None = None


@dataclass(frozen=True)
class AfterStepCtx:
    """Immutable step observation; modules request stopping through export slots.

    ``context_tokens_estimate`` measures the step's next request with the host's
    unified input budget. ``input_limit_tokens`` is that budget's hard input
    limit for the current model (window minus output reservation and safety
    margin); ``None`` when the host has no budget for the model.
    """

    session_key: str
    channel: str
    chat_id: str
    iteration: int
    context_tokens_estimate: int
    tools_called: tuple[str, ...]
    partial_reply: str
    tools_used_so_far: tuple[str, ...]
    tool_chain_partial: tuple[dict[str, object], ...]
    partial_thinking: str | None
    has_more: bool
    early_stop: bool = False
    early_stop_reason: str = ""
    extra_metadata: dict[str, object] = field(default_factory=dict)
    input_limit_tokens: int | None = None


@dataclass
class AfterReasoningCtx:
    """Reply gate snapshot with writable reply, media and outbound metadata."""

    session_key: str
    channel: str
    chat_id: str
    tools_used: tuple[str, ...]
    thinking: str | None
    response_metadata: ResponseMetadata
    streamed: bool
    tool_chain: tuple[dict[str, object], ...]
    context_retry: dict[str, object]
    reply: str
    media: list[str] = field(default_factory=list)
    meme_tag: str | None = None
    outbound_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AfterToolResultCtx:
    """Final tool result observed by plugin lifecycle subscribers."""

    session_key: str
    channel: str
    chat_id: str
    tool_name: str
    arguments: dict[str, object]
    result: str
    status: str


@runtime_checkable
class BeforeTurnObservation(Protocol):
    """Read-only retrieval fields needed by memory inspection modules."""

    @property
    def session_key(self) -> str: ...
    @property
    def channel(self) -> str: ...
    @property
    def chat_id(self) -> str: ...
    @property
    def content(self) -> str: ...
    @property
    def timestamp(self) -> datetime: ...
    @property
    def retrieved_memory_block(self) -> str: ...
    @property
    def retrieval_trace_raw(self) -> object | None: ...


@dataclass
class PromptRenderCtx:
    """Prompt gate fields shared by role reaction contributions."""

    # render/before-step ctx 走 GATE 链，插件可直接改写字段影响后续阶段。
    # read-only by convention
    session_key: str
    channel: str
    chat_id: str
    content: str
    media: list[str] | None
    timestamp: datetime
    history: list[dict[str, object]]
    skill_names: list[str] | None
    retrieved_memory_block: str
    disabled_sections: set[str]
    turn_injection_prompt: str
    session_metadata: dict[str, object] = field(default_factory=dict)
    extra_hints: list[str] = field(default_factory=list)
    # writable
    system_sections_top: list[PromptSectionRender] = field(default_factory=list)
    system_sections_bottom: list[PromptSectionRender] = field(default_factory=list)
