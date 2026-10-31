"""Turn events, ``COMMANDS``, and the initiated-delivery socket (D19, #902).

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

from shiori_sdk.accounts.targets import AccountTarget
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

    Nothing is writable.
    """

    session_key: str
    channel: str
    chat_id: str
    reply: str
    tools_used: tuple[str, ...]
    thinking: str | None
    will_dispatch: bool


type CommandHandler = Callable[[CommandInput], Awaitable[str]]
"""Answers one command turn; the returned text is the turn's reply."""


class Commands(Protocol):
    """Bot commands, answered right after the session is acquired.

    A message whose head is ``/name`` (any case, an ``@bot`` suffix and
    arguments allowed, see ``shiori_sdk.commands.command_name``) is answered by
    the handler registered under ``name``, ahead of the memory backlog guard; a
    command turn retrieves no memory and calls no model. Other messages, and
    commands nobody registered, are ordinary turns.
    """

    def register(
        self, name: str, handler: CommandHandler, *, description: str | None = None
    ) -> Callable[[], None]:
        """Answers ``/name`` with ``handler`` and returns the registration's removal.

        ``name`` is lowercase, without the leading slash, whitespace or ``@``;
        a name already registered raises ``ValueError``. ``description`` puts
        the command in the command menu channels show; an alias leaves it None.
        Hand the removal to ``ctx.effect`` so unloading the plugin removes the
        command.
        """
        ...


COMMANDS: Key[Commands] = Key("commands")
"""Provided by the core conversation module; plugins declare it in ``inject``."""


@dataclass(frozen=True, kw_only=True)
class InitiatedMessageCommitted:
    """A role message the user did not ask for was stored on the role session.

    The host emits this after the message is committed, so ``message_id``
    names a stored message. Two publishers emit it:

    - initiated delivery (``CONVERSATION`` / ``PROACTIVE_HOST.deliver``, and
      the host's own proactive loop until it moves into the plugin), once per
      delivered reply. A natural sequence emits once for the delivered
      messages: ``message_id`` is the last one and ``assistant_response``
      their texts joined by a blank line. ``tools_used`` is
      ``("message_push",)``.
    - a host-owned push (the ``account_send`` tool reaching an external chat
      outside a live turn), once per push. ``tools_used`` names the tool.

    ``thread_id`` is the conversation thread the message belongs to; a role's
    session mixes threads, so subscribers read history with it.

    ``source`` names who started the message: the ``InitiatedReply.source``
    a plugin passed (by convention its plugin id; the host's proactive loop
    and Drift use ``"proactive"``), or ``"push"`` for a host-owned push.

    Plugins watch it; they do not construct it.
    """

    session_key: str
    channel: str
    role_id: str
    thread_id: str
    source: str
    chat_id: str = ""
    assistant_response: str = ""
    tools_used: tuple[str, ...] = ()
    message_id: str = ""


def _freeze(mapping: Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(mapping, MappingProxyType):
        return mapping
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True, kw_only=True)
class InitiatedToolFact:
    """One tool call stored beside a natural reply sequence.

    ``message_push``, ``finish_turn`` and ``finish_drift`` are delivery
    controls, not facts, and are not stored.
    """

    call_id: str
    name: str
    arguments: Mapping[str, object]
    result: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze(self.arguments))


@dataclass(frozen=True, kw_only=True)
class InitiatedReply:
    """One initiated reply, including its target, media and natural sequence.

    The reply speaks for the role that owns ``session_key``, which must be
    exactly a role session key (``role:<role_id>``); any other key raises
    ``ValueError``. The target must be one that role can reach: its own
    desktop chat (``channel="desktop"``, ``chat_id="role:<role_id>"``; another
    desktop chat raises ``ValueError`` before anything is written), a private chat
    with the bound user through one of its online accounts, or an
    ``account_target`` sent through the role's account on
    ``account_channel``. Both account fields are given together or not at
    all. With an account target, ``channel`` / ``chat_id`` name the chat the
    reply is recorded under; a sequence first opens there, so for a sequence
    they must also be a chat the role can reach.

    ``expected_mood_updated_at`` and ``moods`` are the
    ``PROACTIVE_HOST.reply_state(role_id)`` the caller read when its work
    started. The mood and thought are validated against ``moods``. When the
    role's stored mood changed after that read (a passive reply landed in
    between) the reply is stale: a single reply raises without sending; a
    sequence is still sent and stored, but its mood and thought do not
    replace the newer state.

    ``content`` is the text stored on the role session. When ``messages`` is
    non-empty it must equal those texts joined by a blank line, and natural
    chat must be on for the role; delivery then sends each text as its own
    message and stores them in order. Media rides on the first message.
    ``tool_facts`` ride along with ``messages`` only.

    The stored messages are marked ``proactive`` with source ``proactive`` and
    ``tools_used=["message_push"]`` whatever ``source`` says; ``source`` only
    reaches ``InitiatedMessageCommitted``. They carry no evidence item ids.

    Fields may still be added or removed until the proactive loop runs on
    this type (P6b-4b); they are fixed when SDK 4.0 is released.
    """

    session_key: str
    content: str
    source: str
    channel: str
    chat_id: str
    mood: str
    thought: str
    expected_mood_updated_at: str
    moods: tuple[str, ...]
    media: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    account_channel: str = ""
    account_target: AccountTarget | None = None
    tool_facts: tuple[InitiatedToolFact, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.account_channel) != (self.account_target is not None):
            raise ValueError("account_channel 与 account_target 必须同时给出")
        object.__setattr__(self, "moods", tuple(self.moods))
        object.__setattr__(self, "media", tuple(self.media))
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "tool_facts", tuple(self.tool_facts))


@dataclass(frozen=True, kw_only=True)
class InitiatedDelivery:
    """What one initiated delivery stored.

    ``message_ids`` are the committed messages, in order. ``complete`` is
    True only when every message of the reply was sent and stored.

    An incomplete result is not an error. For a single reply it means the
    transport refused it (the desktop did not accept the message) and nothing
    was stored. For a sequence it means a newer user message
    in that chat, the role's removal or natural chat being switched off
    stopped it: the prefix already sent is stored and announced (possibly
    none), the rest is dropped.
    """

    message_ids: tuple[str, ...]
    complete: bool


class Conversation(Protocol):
    """Deliver a reply the host initiated, outside a user turn.

    The host provides this key for the generation it belongs to. 4.x cannot
    add methods to this protocol later (D19).
    """

    async def deliver_initiated_reply(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Send ``reply``, store what was sent, and emit ``InitiatedMessageCommitted``.

        Returns what was stored (see ``InitiatedDelivery``). Raises before
        writing anything when the session is not a role session, the role is
        gone, a desktop target is not the role's own, the reply fails validation against ``reply.moods``, natural chat
        is off for a multi-message reply, tool facts arrive without that
        sequence, or a single reply is stale (``expected_mood_updated_at``).

        Raises when a send fails or is refused mid-way. A single reply then
        stores nothing. A sequence keeps the prefix already sent (stored and
        announced), and the first message of a refused desktop sequence
        raises instead of returning an empty result. Account sends that fail
        or whose outcome is unknown stay on the session as delivery records
        marked ``failed`` / ``uncertain``, outside the conversation history.

        A sequence needs a runtime lease or an already bound channel-sequence
        owner.
        """
        ...


CONVERSATION: Key[Conversation] = Key("conversation")
"""Initiated delivery for one generation. The host provides this."""
