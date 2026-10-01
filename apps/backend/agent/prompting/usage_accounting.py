"""Keep individual request facts separate from billed totals for one turn."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict

_calls: ContextVar[list[dict] | None] = ContextVar("turn_usage_calls", default=None)


@contextmanager
def turn_usage():
    """Collect only calls made within this async turn, including auxiliary work."""
    token = _calls.set([])
    try:
        yield
    finally:
        _calls.reset(token)


def record_usage(response, *, purpose: str) -> None:
    """Record unknown usage as None, even when another call returned actual usage."""
    calls = _calls.get()
    if calls is None:
        return
    calls.append(
        {
            "purpose": purpose,
            "model": response.model,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "cache_hit_tokens": response.cache_hit_tokens,
            "total_tokens": response.total_tokens,
            "budget": asdict(response.input_budget) if response.input_budget else None,
        }
    )


def current_usage() -> dict:
    """Return last conversation input and explicitly partial cumulative billing."""
    calls = list(_calls.get() or [])
    conversation = [call for call in calls if call["purpose"] == "default"]
    totals = {}
    for field in (
        "prompt_tokens",
        "completion_tokens",
        "cache_hit_tokens",
        "total_tokens",
    ):
        values = [call[field] for call in calls if call[field] is not None]
        totals[field] = sum(values) if values else None
        totals[f"{field}_unknown_calls"] = len(calls) - len(values)
    return {
        "calls": calls,
        "last_request": conversation[-1] if conversation else None,
        "cumulative": totals,
    }
