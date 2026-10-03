"""Validated visible-output accounting for OpenAI-compatible responses."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OutputTokenUsage:
    """Provider counts; visible tokens exclude explicitly reported reasoning."""

    completion_tokens: int | None
    reasoning_tokens: int | None
    visible_tokens: int | None
    unavailable_reason: str = ""


def _field(value: Any, key: str):
    return value.get(key) if isinstance(value, dict) else getattr(value, key, None)


def _count(value: Any):
    return value if type(value) is int and value >= 0 else None


def parse_output_usage(usage: Any, *, has_thinking: bool = False) -> OutputTokenUsage:
    """Use strict counts, rejecting ambiguous or inconsistent reasoning usage.

    Without reasoning details or observed thinking, completion is a conservative
    upper bound on visible output: any unreported hidden reasoning remains included.
    """
    raw_completion = _field(usage, "completion_tokens")
    completion = _count(raw_completion)
    raw_reasoning = _field(
        _field(usage, "completion_tokens_details"), "reasoning_tokens"
    )
    reasoning = _count(raw_reasoning)
    reason = ""
    if completion is None or completion == 0:
        reason = (
            "missing_completion_usage"
            if raw_completion is None
            else "invalid_completion_usage"
        )
    elif raw_reasoning is not None and (reasoning is None or reasoning >= completion):
        reason = "invalid_reasoning_usage"
    elif has_thinking and reasoning is None:
        reason = "missing_reasoning_usage"
    return OutputTokenUsage(
        completion, reasoning, None if reason else completion - (reasoning or 0), reason
    )
