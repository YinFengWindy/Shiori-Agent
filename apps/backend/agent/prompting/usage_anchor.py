"""Request-scoped usage anchors; never store a role's cumulative billed usage."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps

from .assembler import SYSTEM_CONTEXT_FRAME_MARKER
from .token_estimate import estimate_tokens
from .usage_accounting import turn_usage

_context: ContextVar[tuple | None] = ContextVar("input_usage_context", default=None)
_independent_anchors: ContextVar[UsageAnchors | None] = ContextVar(
    "independent_usage_anchors", default=None
)


@contextmanager
def usage_context(key: tuple):
    """Bind model calls to an immutable actual visible-context identity."""
    token = _context.set(key)
    try:
        yield
    finally:
        _context.reset(token)


@contextmanager
def independent_usage_context():
    """Give a one-off child its own visible request and temporary anchor ownership."""
    token = _independent_anchors.set(UsageAnchors())
    try:
        with usage_context(("independent-task",)), turn_usage():
            yield
    finally:
        _independent_anchors.reset(token)


def request_anchors(shared: UsageAnchors) -> UsageAnchors:
    """Choose a child's temporary store or the provider's retained conversation store."""
    return _independent_anchors.get() or shared


def turn_usage_context(function):
    """Scope a reasoner turn to shared user history or one external conversation."""

    @wraps(function)
    async def wrapped(self, *args, **kwargs):
        session = kwargs["session"]
        view = kwargs.get("context_view")
        key = (session.key,)
        if view is not None:
            key += (
                view.scope,
                view.thread_id,
                tuple(sorted(view.user_threads.bound_chat_thread_ids)),
            )
        with usage_context(key), turn_usage():
            return await function(self, *args, **kwargs)

    return wrapped


@dataclass(frozen=True)
class InputEstimate:
    """Single-request input tokens and their provenance."""

    tokens: int
    source: str


@dataclass
class _Anchor:
    request: dict
    prompt_tokens: int


def _stable_messages(request: dict) -> list[dict]:
    # Only owned, explicitly marked frames are replaceable. Arbitrary user text,
    # system prompt edits, and rewrites of prior history invalidate the anchor.
    return [
        message
        for message in request.get("messages", [])
        if not (
            message.get("role") == "user"
            and isinstance(message.get("content"), str)
            and message["content"].startswith(SYSTEM_CONTEXT_FRAME_MARKER)
        )
    ]


def input_cost(request: dict) -> int:
    """Count only provider input, excluding connection identity and generation knobs."""
    return estimate_tokens(
        {
            k: v
            for k, v in request.items()
            if k in {"messages", "tools", "response_format"}
        }
    )


class UsageAnchors:
    """Calibrate append-only requests and reject responses superseded in flight."""

    def __init__(self) -> None:
        self._anchors: dict[tuple, _Anchor] = {}
        self._pending: dict[tuple, object] = {}
        self._views: dict[tuple, tuple] = {}

    def _key(self, request: dict) -> tuple | None:
        context = _context.get()
        if context is None:
            return None
        key = context[:3]
        if self._views.get(key) != context:
            self._anchors.pop(key, None)
            self._pending.pop(key, None)
            self._views[key] = context
        return key

    def estimate(self, request: dict) -> InputEstimate:
        """Use exact usage, a verified prefix delta, or a fresh local estimate."""
        local = input_cost(request)
        key = self._key(request)
        anchor = self._anchors.get(key) if key is not None else None
        if anchor is None:
            return InputEstimate(local, "local")
        if anchor.request == request:
            return InputEstimate(anchor.prompt_tokens, "actual")
        previous = _stable_messages(anchor.request)
        current = _stable_messages(request)
        # Tools/response-format changes are deliberately invalidated; no schema
        # addition can be mistaken for a free append. Known context frames use
        # the full old/new cost difference, including insertion and removal.
        old_other = {k: v for k, v in anchor.request.items() if k != "messages"}
        new_other = {k: v for k, v in request.items() if k != "messages"}
        if old_other == new_other and current[: len(previous)] == previous:
            return InputEstimate(
                max(0, anchor.prompt_tokens + local - input_cost(anchor.request)),
                "anchor_delta",
            )
        if key is not None:
            self._anchors.pop(key, None)
            self._pending.pop(key, None)
        return InputEstimate(local, "local")

    def begin(self, request: dict) -> tuple[tuple | None, object, dict]:
        """Snapshot the exact outgoing input before awaiting network or callbacks."""
        key = self._key(request)
        ticket = object()
        if key is not None:
            self._pending[key] = ticket
        return key, ticket, deepcopy(request)

    def finish(
        self, ticket: tuple[tuple | None, object, dict], prompt_tokens: int | None
    ) -> None:
        """Only the latest matching request may replace that context's anchor."""
        key, identity, request = ticket
        if key is None or self._pending.get(key) is not identity:
            return
        self._pending.pop(key, None)
        if prompt_tokens is not None:
            self._anchors[key] = _Anchor(request, prompt_tokens)
