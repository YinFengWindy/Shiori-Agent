"""``PROACTIVE_HOST``: host services a proactive tick calls (P6b, #907).

The port is process-wide. Calls that run or deliver work pin the currently
published generation, the way an incoming message does, and wait while no
generation admits work. A caller that already holds a lease keeps that lease.
Reads use the current lease's generation when there is one, otherwise the
published generation, and do not wait.

A tick whose role has natural chat on opens one reply scope for the whole
tick. The scope, its invalidation and its tool facts stay together: facts are
committed before the scope ends, including when the plan is invalidated.
Choosing a target reads candidate chats, the last user message on a thread
and whether the user is at the desktop. Tool schemas and connected MCP server
names come from the generation's registry. Session history reads return the
role session's recent user-context turns and recent proactive messages.

This key and ``InitiatedReply`` may still gain or lose members until the
proactive loop moves into its plugin; they are fixed when SDK 4.0 is released.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal, Protocol

from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from shiori_sdk.core.tools import ToolStatus
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
class RoleReplyState:
    """The role's mood catalog and when its current mood was last stored.

    Read it when a tick starts and copy both fields into ``InitiatedReply``
    (``moods`` and ``expected_mood_updated_at``).
    """

    moods: tuple[str, ...]
    mood_updated_at: str


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
    """One proactive message already stored on the role session."""

    content: str
    timestamp: datetime | None
    state_summary_tag: str
    source_refs: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_refs",
            tuple(_freeze(ref) for ref in self.source_refs),
        )


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
        """
        ...

    async def deliver(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Deliver ``reply`` on the published generation.

        Same payload, result and errors as
        ``CONVERSATION.deliver_initiated_reply``. Pins a lease so a
        process-level loop does not keep a previous generation's conversation.
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

    def reply_state(self, role_id: str) -> RoleReplyState:
        """Moods the role may use, and the stored mood's timestamp.

        Raises ``ValueError`` when the role is gone.
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

        Raises ``ValueError`` when the role is gone, the mood is outside the
        catalog, the thought is not a short first-person line, or required
        text is blank.
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

    async def commit_natural_reply(self, reply: InitiatedReply) -> InitiatedDelivery:
        """Deliver ``reply`` through the natural plan already open on this task.

        Does not open another scope. ``deliver`` would, and a second scope
        drops the tick's plan. No open plan raises ``RuntimeError``. The
        event is emitted before this returns; success and failure side
        effects belong to the caller and therefore follow the event.
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

    def bound_chat_target(
        self, role_id: str, channel: str, chat_id: str
    ) -> tuple[str, AccountTarget]:
        """The account plugin and private target that reach a bound user's chat.

        Raises ``LookupError`` when that chat is not a bound online chat of
        the role.
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

        ``natural_draft`` runs the open natural plan's one format correction
        before returning. The plan keeps the provider response (refusal,
        finish reason, provider fields). The returned completion is the
        corrected tool call. No open plan raises.
        """
        ...


PROACTIVE_HOST: Key[ProactiveHost] = Key("proactive_host")
"""Proactive ticks, delivery and the host facts they read. The host provides this."""
