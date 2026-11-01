"""Reply and turn results owned by the proactive plugin.

These mirror the fields the tick constructs. Host code that only reads the
same attributes can pass its own objects through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class InvalidRoleReply(ValueError):
    """A final reply cannot be committed as the role's current state."""


@dataclass(frozen=True)
class RoleReply:
    """Dialogue plus the role's mood and first-person thought."""

    content: str
    mood: str
    thought: str


@dataclass(frozen=True)
class RoleReplyContext:
    """Moods and the stored mood time captured before generation."""

    moods: tuple[str, ...]
    previous_updated_at: str


@dataclass
class TurnOutbound:
    session_key: str
    content: str
    media: list[str] = field(default_factory=list)


@dataclass
class TurnTrace:
    source: Literal["passive", "proactive"]
    model: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    retrieval: dict | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    decision: Literal["reply", "skip"]
    outbound: TurnOutbound | None
    evidence: list[str] = field(default_factory=list)
    trace: TurnTrace | None = None
    side_effects: list[Any] = field(default_factory=list)
    success_side_effects: list[Any] = field(default_factory=list)
    failure_side_effects: list[Any] = field(default_factory=list)
    role_reply: RoleReply | None = None
    reply_context: RoleReplyContext | None = None
