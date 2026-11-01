"""``PROACTIVE_HOST``: host services a proactive tick calls (P6b, #907).

The port is process-wide. Calls that run or deliver work pin the currently
published generation, the way an incoming message does, and wait while no
generation admits work. A caller that already holds a lease keeps that lease.
Reads use the current lease's generation when there is one, otherwise the
published generation, and do not wait.

A tick whose role has natural chat on opens one reply scope for the whole
tick. The scope, its invalidation, its tool facts and its delivery stay
together: tool calls run through ``execute_tool`` are recorded on the open
plan and committed before the scope ends, including when the plan is
invalidated. Choosing a target reads candidate chats, the last user message on
a thread and whether the user is at the desktop. Host tools run through
``run_host_tool``; their schemas and the connected MCP servers come from the
generation's registry. Session history reads return the role session's recent
user-context turns and recent proactive messages. The reply stamp (mood
catalog and stored mood time) is ``CONVERSATION.reply_state``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal, Protocol

from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from shiori_sdk.core.tools import ToolStatus
from shiori_sdk.tools import ToolResult
from shiori_sdk.kernel import Key


def _freeze(mapping: Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(mapping, MappingProxyType):
        return mapping
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True, kw_only=True)
class ProactiveToolCall:
    """One model tool call the proactive loop wants the host to run.

    ``arguments`` are the model's arguments, before plugins rewrite them.
    """

    call_id: str
    name: str
    arguments: Mapping[str, object]
    session_key: str = ""
    channel: str = ""
    chat_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze(self.arguments))


@dataclass(frozen=True, kw_only=True)
class ProactiveToolOutcome:
    """How one checked tool call ended.

    ``arguments`` are the arguments the tool ran with (or the model's, when
    the call was denied). ``text`` is ``str()`` of what the invoker returned,
    the text the host's proactive tool loop records today, or the denial
    reason. ``finalize`` asks the loop to stop, and is only set on a denial.
    """

    text: str
    status: ToolStatus
    arguments: Mapping[str, object]
    finalize: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze(self.arguments))


type ProactiveToolInvoker = Callable[[str, Mapping[str, object]], Awaitable[object]]
"""Runs the tool with the final arguments. The host calls it only after the
core checks allow the call."""


@dataclass(frozen=True, kw_only=True)
class CompletionToolCall:
    """One tool call parsed from a model completion.

    With ``defer_tool_argument_errors`` a call whose arguments did not parse
    keeps ``arguments`` empty, the model's text in ``raw_arguments`` and the
    parse error in ``arguments_error``; such a call must not be executed.
    """

    id: str
    name: str
    arguments: Mapping[str, object]
    raw_arguments: str | None = None
    arguments_error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze(self.arguments))


@dataclass(frozen=True, kw_only=True)
class ModelCompletion:
    """A chat completion for the proactive loop.

    ``content`` is empty when the model returned no text. ``thinking`` is the
    provider's reasoning text when it returned one.
    """

    content: str
    tool_calls: tuple[CompletionToolCall, ...] = ()
    thinking: str | None = None


@dataclass(frozen=True, kw_only=True)
class ValidatedRoleReply:
    """A reply the host accepted as the role's current mood and thought."""

    content: str
    mood: str
    thought: str


class NaturalReplyInvalidated(RuntimeError):
    """The open natural reply was superseded before it was sent.

    Raised from ``natural_reply_scope`` when the plan is invalidated. Tool
    facts recorded on the plan are already committed.
    """


class NaturalReplyTicket(Protocol):
    """One natural reply, from the moment the tick accepts it until it ends.

    ``begin_natural_reply`` returns the only tickets ``natural_reply_scope``
    accepts. ``invalidate`` stops the plan once; calling it again does not
    cancel cleanup that has already started.
    """

    def invalidate(self) -> None:
        """Stop this reply at the next safe boundary."""
        ...


@dataclass(frozen=True, kw_only=True)
class CandidateChat:
    """One chat that may receive the role's next proactive message.

    Desktop is first. The rest are private chats with the bound user through
    the role's online accounts, in binding order.
    """

    channel: str
    chat_id: str


@dataclass(frozen=True, kw_only=True)
class RecentTurnMessage:
    """One user or assistant turn from the role's user-context history.

    ``content`` is truncated to 200 characters. Context frames are omitted.
    """

    role: str
    content: str
    timestamp: str


@dataclass(frozen=True, kw_only=True)
class ProactiveHistoryMessage:
    """One proactive message already stored on the role session.

    ``timestamp`` is None when the stored time is missing or unreadable.
    """

    content: str
    timestamp: datetime | None


class ProactiveHost(Protocol):
    """Host services for a proactive tick. The host provides this."""

    async def run_tick[T](
        self, role_id: str, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Run ``operation`` as the role's proactive tick.

        The tick is serialized with the role's other work, under the role's
        desktop thread, with the role's chat model snapshot active: a
        ``complete`` call inside ``operation`` uses that model. A missing role
        raises before ``operation`` runs.
        """
        ...

    def passive_turn_busy(self, role_id: str) -> bool:
        """Whether a passive turn is in progress for the role's session.

        False when the runtime is not up. This does not wait for admission.
        """
        ...

    async def execute_tool(
        self, call: ProactiveToolCall, invoker: ProactiveToolInvoker
    ) -> ProactiveToolOutcome:
        """Run one tool call through the published generation's kernel.

        The kernel's ``ToolCalling`` chain and the core checks see the call.
        A denied call does not run ``invoker``. The caller owns the loop.

        Inside a natural reply scope that has a plan, the call (with the
        model's arguments) and ``outcome.text`` are recorded on the plan as a
        tool fact, a denied call included. ``message_push``, ``finish_turn``
        and ``finish_drift`` are delivery controls and are not recorded. The
        scope commits the facts when it ends.
        """
        ...

    async def run_host_tool(
        self, name: str, arguments: Mapping[str, object], *, role_id: str
    ) -> str | ToolResult:
        """Run the generation's registered tool ``name`` for ``role_id``.

        Only inside an ``execute_tool`` invoker, for the tool name the kernel
        checks just allowed; any other call raises ``PermissionError`` without
        running anything, so a host tool never skips the core checks. The
        tool runs in the role's user context:
        a tool that takes the role, the turn session or the thread from its
        execution context gets the role, the role's session and its desktop
        thread, and the model cannot override them. No other context is
        passed. Returns what the tool returned; a tool that raises returns its
        error text. An unregistered ``name`` raises ``LookupError``; an empty
        ``role_id`` raises ``ValueError``.
        """
        ...

    async def deliver(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Deliver ``reply`` on the published generation.

        Outside a natural reply plan: same payload, result and errors as
        ``CONVERSATION.deliver_initiated_reply``.

        Inside the natural reply plan open on this task, ``reply`` is the
        tick's single draft and goes out through that plan, as the messages
        the plan accepted from ``complete(natural_draft=True)``; no second
        scope is opened. ``reply.session_key`` must be the scope's session and
        ``channel`` / ``chat_id`` the chat the scope opened on or was last
        moved to by ``retarget_natural_transport``. A reply with
        ``messages``, ``tool_facts`` or an account target is refused too: the
        plan carries the messages and the facts, and ``retarget_natural_reply``
        sets the account target. A refused reply raises ``ValueError`` before
        anything is written.

        Once part of the reply is stored, the result reports it even when the
        caller's task is cancelled, or the open plan is interrupted, while
        the rest is being sent: ``deliver`` returns what was stored and the
        cancellation is raised again at the caller's next ``await``. When
        nothing was stored yet, the cancellation propagates. A failure of the
        host's own bookkeeping after the whole reply was stored (any exception
        from then on: presence, affection, role gate reacquisition, the final
        mood write, the committed event) is logged by the host and the result
        stays complete. Any other exception means the reply was not stored in
        full.
        """
        ...

    def user_at_desktop(self) -> bool:
        """Whether the desktop host last reported the user as present.

        True until the first report. This does not change the report.
        """
        ...

    def recent_activity(self, role_id: str, *, now: datetime) -> str:
        """External chats' recent activity around ``now``, or empty."""
        ...

    def compile_role_prompt(self, role_id: str) -> str:
        """The role prompt proactive turns use, including channel identities.

        Raises ``ValueError`` when the role is gone or the prompt is empty.
        """
        ...

    def validate_reply(
        self,
        role_id: str,
        *,
        content: str,
        mood: str,
        thought: str,
        allow_empty_content: bool = False,
    ) -> ValidatedRoleReply:
        """Validate one reply against the role's mood catalog.

        The catalog is ``CONVERSATION.reply_state`` of the generation this
        call runs on: the lease the caller holds (inside ``run_tick``, the
        tick's), otherwise the published one. Raises ``ValueError`` when the role is gone, the
        mood is outside the catalog, the thought is not a short first-person
        line, or required text is blank.
        """
        ...

    def natural_chat_enabled(self, session_key: str) -> bool:
        """Whether the role that owns ``session_key`` has natural chat on.

        The role record is read now. A missing role is off. The session copy
        of the role config is not the switch.
        """
        ...

    def begin_natural_reply(self) -> NaturalReplyTicket:
        """Open the ticket for one natural reply, before its scope starts.

        The caller invalidates this ticket to stop the reply, including from
        outside the task that is inside ``natural_reply_scope``.
        """
        ...

    def natural_reply_scope(
        self,
        ticket: NaturalReplyTicket,
        session_key: str,
        channel: str,
        chat_id: str,
        *,
        turn_id: str,
    ) -> AbstractAsyncContextManager[None]:
        """Bind ``ticket`` for one tick and commit its tool facts on the way out.

        Facts are committed while the plan is still current, including when
        the body raises ``NaturalReplyInvalidated``. A ticket this host did
        not issue raises ``TypeError``. With natural chat off, the ticket is
        invalidated and the body runs without a plan.
        """
        ...

    def reply_invalidated(self) -> bool:
        """Whether the natural reply bound on this task has been superseded."""
        ...

    async def retarget_natural_reply(
        self, session_key: str, target: Mapping[str, object]
    ) -> None:
        """Point the open natural reply at an explicit account target.

        ``target`` is the account-target mapping ``message_push`` recorded.
        No open plan does nothing.
        """
        ...

    async def retarget_natural_transport(
        self, session_key: str, channel: str, chat_id: str
    ) -> None:
        """Point the open natural reply at another candidate chat.

        No open plan, or a plan already aimed at that chat, does nothing.
        """
        ...

    def natural_reply_active(self) -> bool:
        """Whether this task is inside a natural-reply scope that has a plan."""
        ...

    def natural_reply_properties(self) -> Mapping[str, object]:
        """JSON-schema properties of a natural draft's message list.

        The draft tool puts these in place of its single message field and
        requires ``messages``. They do not depend on an open plan.
        """
        ...

    def natural_reply_messages(self) -> tuple[str, ...] | None:
        """The message list the open plan accepted from the last natural draft.

        None until ``complete(natural_draft=True)`` accepted one. No open plan
        raises ``RuntimeError``.
        """
        ...

    def candidate_chats(self, role_id: str) -> tuple[CandidateChat, ...]:
        """Desktop first, then private chats with the bound user.

        Does not consult the proactive switch: a preview may pass candidates
        for a role whose saved switch is still off. A missing role raises
        ``KeyError``.
        """
        ...

    def last_user_message_at(
        self, role_id: str, channel: str, chat_id: str
    ) -> datetime | None:
        """When the user last wrote in that chat, or None.

        Timestamps are timezone-aware. A naive legacy value was local time
        and is converted. Target selection ignores the desktop chat.
        """
        ...

    def tool_schemas(
        self, names: Sequence[str] | None = None
    ) -> tuple[Mapping[str, object], ...]:
        """Schemas of the generation's registered tools.

        ``names`` is None for every tool, in registration order. A sequence
        keeps the caller's order and skips names that are not registered.
        """
        ...

    def mcp_server_names(self) -> tuple[str, ...]:
        """MCP servers that currently have tools on the generation, sorted."""
        ...

    def mcp_tool_names(self, server: str) -> tuple[str, ...]:
        """Names of the tools ``server`` currently has on the generation, sorted.

        Empty when the server is unknown or not connected.
        """
        ...

    def require_channel_account(self, role_id: str, channel: str) -> None:
        """Raise unless ``role_id`` has an account on ``channel``.

        The same check a proactive retarget makes before it keeps the draft.
        No account-send tool raises ``RuntimeError``. No account raises
        ``LookupError``.
        """
        ...

    def recent_messages(
        self, role_id: str, *, limit: int
    ) -> tuple[RecentTurnMessage, ...]:
        """Recent user-context turns on the role session, oldest first.

        User and assistant messages with text, without context frames.
        """
        ...

    def recent_proactive_messages(
        self, role_id: str, *, limit: int = 5
    ) -> tuple[ProactiveHistoryMessage, ...]:
        """The role session's recent proactive messages, oldest first."""
        ...

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
        tool_choice: str | Mapping[str, object] = "auto",
        max_tokens: int | None = None,
        call_purpose: Literal["default", "auxiliary"] = "default",
        disable_thinking: bool = True,
        defer_tool_argument_errors: bool = False,
        natural_draft: bool = False,
    ) -> ModelCompletion:
        """Complete one chat request on the published model.

        Inside ``run_tick`` the role's chat model snapshot answers and keeps
        its own reasoning effort. Outside a tick the generation's model
        answers through a provider that forces thinking off, or through the
        generation's own provider when no API key is configured; only that
        last case honors ``disable_thinking``. ``max_tokens`` defaults to the
        generation's configured cap. ``call_purpose="auxiliary"`` marks a
        short side request: it opts out of the configured reasoning and does
        not calibrate the input budget. ``tool_choice`` may be ``"auto"`` or
        a tool-choice object.

        ``natural_draft`` turns the completion into the open natural plan's
        draft before returning: the ``message_push`` call's ``messages`` are
        validated, with at most one format correction, and the plan keeps the
        provider response (refusal, finish reason, provider fields). The
        returned completion carries that ``message_push`` call with the
        accepted messages, or unchanged business tool calls the model made
        instead. A completion that cannot become a draft raises
        ``ValueError``. No open plan raises ``RuntimeError``.
        """
        ...

    def builtin_skills_dir(self) -> str:
        """Directory of built-in skills (source tree or the installed resources).

        Drift reads ``SKILL.md`` from here. It does not write state beside those
        files.
        """
        ...

    def file_tool_schema(self, name: str) -> Mapping[str, object]:
        """OpenAI schema of the host file tool ``name`` (``read_file``, ``write_file``, ``edit_file``).

        An unknown name raises ``KeyError``.
        """
        ...

    async def run_drift_file_tool(
        self, role_id: str, name: str, arguments: Mapping[str, object]
    ) -> str | ToolResult:
        """Run file tool ``name`` (see ``file_tool_schema``) for ``role_id``'s Drift.

        Only inside an ``execute_tool`` invoker, for the tool name the kernel
        checks just allowed; any other call raises ``PermissionError`` without
        running anything. The host computes the role's drift directory
        (``roles/<role_id>/drift``): ``write_file`` and ``edit_file`` stay
        inside it, and so does ``read_file`` of a relative path. ``read_file``
        of an absolute path reads that path. A path outside the directory
        returns the tool's error text without touching the file; a tool that
        raises returns ``工具执行出错: ...``. An unknown ``name`` raises
        ``LookupError``; a ``role_id`` that is not one path segment raises
        ``ValueError``.
        """
        ...

    def web_fetch_available(self) -> bool:
        """Whether constructing the host web fetch tool succeeds."""
        ...

    async def fetch_url(self, url: str, *, format: str = "text") -> str:
        """Fetch ``url`` and return the tool's JSON text.

        ``web_fetch_available`` is false when this cannot be constructed.
        """
        ...

    def tool_resource_scope(self) -> AbstractAsyncContextManager[None]:
        """Host tool-turn scope for one drift run.

        Nested on the same task does not close twice. Computer-use tools see
        the current tool turn only inside this scope.
        """
        ...

    def configured_max_tokens(self) -> int:
        """The generation's configured completion cap.

        The current lease's generation when there is one, otherwise the
        published generation. Does not wait for admission. Raises
        ``RuntimeError`` when the runtime is not up.
        """
        ...


PROACTIVE_HOST: Key[ProactiveHost] = Key("proactive_host")
"""Proactive ticks, delivery and the host facts they read. The host provides this."""
