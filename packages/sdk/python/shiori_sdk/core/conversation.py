"""Turn events of the core conversation module and its ``COMMANDS`` socket (#902).

The host emits one event per turn stage through the plugin kernel: ``on``
handlers run in plugin order and may return a replaced event, the core's
fixed checks run on the final one, then ``watch`` handlers see it. Every event
is a frozen projection of the host's turn state, never the state itself: the
host applies only the fields documented as *writable* back to the turn and
ignores changes to the others. Container fields are tuples, frozensets or
read-only mappings.

``Veto`` stops a stage where it can stop: it aborts the turn with
``Veto.reason`` as the reply (``TurnStarting``, ``ReasoningStarting``) or ends
the tool loop with it (``StepStarting``). The other events cannot be vetoed;
a veto there fails the turn. A vetoed event reaches no watcher.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal, Protocol

from shiori_sdk.commands import CommandInput
from shiori_sdk.kernel import Key
from shiori_sdk.prompting import PromptSectionRender

type ContextScope = Literal["user", "external"]
"""Which context a role turn belongs to: the user's own, or an external chat."""

type ReplyMode = Literal["single", "sequence"]
"""One reply message, or a sequence of messages delivered one by one."""


def _no_metadata() -> Mapping[str, object]:
    return MappingProxyType({})


@dataclass(frozen=True)
class ConversationMessage:
    """One message of a turn's history window."""

    role: str
    content: str
    tools_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class TurnStarting:
    """A turn has its session, history and retrieved memory; reasoning has not begun.

    ``context_scope`` is None outside a role's shared session. ``history`` is
    the turn's history window, oldest first. ``retrieval_trace`` is the memory
    engine's own trace of the retrieval (a top-level container frozen), None
    without one.

    Writable: ``skill_names``, ``extra_hints`` (passed on to the reasoning)
    and ``extra_metadata`` (merged into the reply's outbound metadata).
    """

    session_key: str
    channel: str
    chat_id: str
    content: str
    timestamp: datetime
    context_scope: ContextScope | None
    history: tuple[ConversationMessage, ...]
    retrieved_memory_block: str
    retrieval_trace: object | None
    skill_names: tuple[str, ...] = ()
    extra_hints: tuple[str, ...] = ()
    extra_metadata: Mapping[str, object] = field(default_factory=_no_metadata)


@dataclass(frozen=True)
class ReasoningStarting:
    """The turn is about to reason with the retrieved memory and skills.

    Writable: ``skill_names``, ``retrieved_memory_block`` and ``extra_hints``.
    """

    session_key: str
    channel: str
    chat_id: str
    content: str
    timestamp: datetime
    skill_names: tuple[str, ...] = ()
    retrieved_memory_block: str = ""
    extra_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptRendering:
    """The prompt of one model request is about to be rendered.

    ``history`` holds the request's history messages in model message form.
    ``supports_reply_sequence`` tells whether this request can deliver a
    message sequence at all; ``minimal_request`` marks the host's last-resort
    request, which renders no plugin sections or hints.

    Writable: ``system_sections_top`` / ``system_sections_bottom`` (rendered
    in order after the core's sections), ``extra_hints`` and ``reply_mode``.
    ``reply_mode`` starts as the role's natural-chat choice; the host renders
    ``"sequence"`` only when the request supports it and is not minimal.
    """

    session_key: str
    channel: str
    chat_id: str
    content: str
    media: tuple[str, ...]
    timestamp: datetime
    context_scope: ContextScope | None
    history: tuple[Mapping[str, object], ...]
    skill_names: tuple[str, ...]
    retrieved_memory_block: str
    disabled_sections: frozenset[str]
    turn_injection_prompt: str
    session_metadata: Mapping[str, object]
    supports_reply_sequence: bool
    minimal_request: bool
    system_sections_top: tuple[PromptSectionRender, ...] = ()
    system_sections_bottom: tuple[PromptSectionRender, ...] = ()
    extra_hints: tuple[str, ...] = ()
    reply_mode: ReplyMode = "single"


@dataclass(frozen=True)
class StepStarting:
    """One model request of the tool loop is about to be sent.

    ``visible_tool_names`` is None when every tool is visible.

    Writable: ``extra_hints`` (appended to this request).
    """

    session_key: str
    channel: str
    chat_id: str
    iteration: int
    input_tokens_estimate: int
    visible_tool_names: frozenset[str] | None
    extra_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepFinished:
    """One step of the tool loop finished; ``has_more`` when tools still run.

    ``context_tokens_estimate`` measures the next request with the host's input
    budget; ``input_limit_tokens`` is the current model's hard input limit,
    None without a budget. ``tool_chain_partial`` holds the tool call groups so
    far as the host records them.

    Writable: ``early_stop`` / ``early_stop_reason`` (closes the turn with a
    summary instead of another step) and ``extra_metadata`` (step telemetry,
    seen only by listeners).
    """

    session_key: str
    channel: str
    chat_id: str
    iteration: int
    context_tokens_estimate: int
    input_limit_tokens: int | None
    tools_called: tuple[str, ...]
    partial_reply: str
    partial_thinking: str | None
    tools_used_so_far: tuple[str, ...]
    tool_chain_partial: tuple[Mapping[str, object], ...]
    has_more: bool
    early_stop: bool = False
    early_stop_reason: str = ""
    extra_metadata: Mapping[str, object] = field(default_factory=_no_metadata)


@dataclass(frozen=True)
class ReasoningFinished:
    """The model's reply is final; it is neither stored nor delivered yet.

    ``reply_messages`` holds the messages of a sequence reply (empty for a
    single reply) and ``reply`` stays their plain join.

    Writable: ``reply``, ``reply_messages``, ``media`` (attachments, in
    order), ``meme_tag`` and ``outbound_metadata``.
    """

    session_key: str
    channel: str
    chat_id: str
    tools_used: tuple[str, ...]
    tool_chain: tuple[Mapping[str, object], ...]
    thinking: str | None
    streamed: bool
    reply: str
    reply_messages: tuple[str, ...] = ()
    media: tuple[str, ...] = ()
    meme_tag: str | None = None
    outbound_metadata: Mapping[str, object] = field(default_factory=_no_metadata)


@dataclass(frozen=True)
class TurnFinished:
    """The turn is stored; ``will_dispatch`` tells whether its reply is sent next.

    ``extra_metadata`` is the turn's telemetry. Nothing is writable.
    """

    session_key: str
    channel: str
    chat_id: str
    reply: str
    tools_used: tuple[str, ...]
    thinking: str | None
    will_dispatch: bool
    extra_metadata: Mapping[str, object] = field(default_factory=_no_metadata)


type CommandHandler = Callable[[CommandInput], Awaitable[str]]
"""Answers one command turn; the returned text is the turn's reply."""


class Commands(Protocol):
    """Bot commands, answered right after the session is acquired.

    A command turn retrieves no memory and calls no model.
    """

    def register(
        self, name: str, handler: CommandHandler, *, description: str | None = None
    ) -> Callable[[], None]:
        """Answers ``/name`` with ``handler`` and returns the registration's removal.

        ``name`` has no leading slash. ``description`` puts the command in the
        command menu channels show; an alias leaves it None. Hand the removal
        to ``ctx.effect`` so unloading the plugin removes the command.
        """
        ...


COMMANDS: Key[Commands] = Key("commands")
"""Provided by the core conversation module (P3-5)."""
