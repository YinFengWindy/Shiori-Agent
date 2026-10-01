"""Lifecycle values and extension protocols shared by plugins and the host."""

from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol


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
    """Immutable step observation; modules request stopping through export slots."""

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
