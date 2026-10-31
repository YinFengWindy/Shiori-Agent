"""``PROACTIVE_HOST``: host services the proactive loop needs (P6b, #907).

The port is process-wide. Calls that run or deliver work pin the currently
published generation, the way an incoming message does, and wait while no
generation admits work. A caller that already holds a lease keeps that lease.
Reads use the current lease's generation when there is one, otherwise the
published generation, and do not wait. The proactive loop still calls the host
directly; switching it onto this port is a later change.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Protocol

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
    the call was denied). ``text`` is the tool's text, or the denial reason.
    ``finalize`` asks the loop to stop, and is only set on a denial.
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
class ModelToolCall:
    """One tool call parsed from a model completion."""

    id: str
    name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze(self.arguments))


@dataclass(frozen=True, kw_only=True)
class ModelCompletion:
    """A chat completion for the proactive loop.

    ``content`` is empty when the model returned no text. ``thinking`` is the
    provider's reasoning text when it returned one.
    """

    content: str
    tool_calls: tuple[ModelToolCall, ...] = ()
    thinking: str | None = None


@dataclass(frozen=True, kw_only=True)
class SkillInfo:
    """A skill the host can load. ``source`` is ``workspace`` or ``builtin``."""

    name: str
    source: str


@dataclass(frozen=True, kw_only=True)
class RoleReplyState:
    """The role's mood catalog and when its current mood was last stored."""

    moods: tuple[str, ...]
    mood_updated_at: str


@dataclass(frozen=True, kw_only=True)
class ValidatedRoleReply:
    """A reply the host accepted as the role's current mood and thought."""

    content: str
    mood: str
    thought: str


class ProactiveHost(Protocol):
    """Host services for a proactive tick. The host provides this."""

    async def run_tick[T](
        self, role_id: str, operation: Callable[[], Awaitable[T]]
    ) -> T:
        """Run ``operation`` as the role's proactive tick.

        The tick is serialized with the role's other work, under the role's
        desktop thread, with the chat model snapshot active. A missing role
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

    async def deliver(self, reply: "InitiatedReply") -> str:
        """Deliver ``reply`` on the published generation.

        Same payload and result as ``CONVERSATION.deliver_initiated_reply``.
        Pins a lease so a process-level loop does not keep a previous
        generation's conversation.
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

    def group_note(self, role_id: str, thread_id: str) -> str:
        """The role's note for one external chat, as a prompt section or empty."""
        ...

    def compile_role_prompt(self, role_id: str) -> str:
        """The role prompt proactive turns use, including channel identities.

        Raises when the role is gone or the prompt is empty.
        """
        ...

    def affection_prompt(self, role_id: str) -> str | None:
        """The affection block, or None while affection is off or uninitialized.

        Raises when the role is gone.
        """
        ...

    def reply_state(self, role_id: str) -> RoleReplyState:
        """Moods the role may use, and the stored mood's timestamp."""
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

        Raises ``ValueError`` when the mood is outside the catalog, the
        thought is not a short first-person line, or required text is blank.
        """
        ...

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        tools: Sequence[Mapping[str, object]] = (),
        tool_choice: str | Mapping[str, object] = "auto",
        disable_thinking: bool = True,
        defer_tool_argument_errors: bool = False,
    ) -> ModelCompletion:
        """Complete one chat request on the published model.

        The fallback provider forces thinking off. An active role model
        snapshot keeps that model's own effort and ignores ``disable_thinking``.
        ``tool_choice`` may be ``"auto"`` or a tool-choice object.
        """
        ...

    def list_skills(self) -> tuple[SkillInfo, ...]:
        """Skills visible to the role. A workspace skill hides a builtin of the same name."""
        ...

    def load_skill(self, name: str) -> str | None:
        """The skill's ``SKILL.md``, workspace first, or None when it is absent."""
        ...

    def render_skills(self, names: Sequence[str]) -> str:
        """Prompt text for ``names``. Unknown names are skipped."""
        ...

    def recent_context(self, role_id: str) -> str:
        """The role's visible recent-context body.

        Empty when the role is gone, the document is missing, unstamped, or
        no longer visible. A missing role does not create a memory directory.
        """
        ...


PROACTIVE_HOST: Key[ProactiveHost] = Key("proactive_host")
"""Proactive ticks, delivery and the host facts they read. The host provides this."""


# Imported for the ``deliver`` annotation. A function-local import would hide
# the name from ``get_type_hints``; the conversation module does not import
# this one.
from shiori_sdk.core.conversation import InitiatedReply as InitiatedReply  # noqa: E402
