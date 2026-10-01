"""Bounded response facts for empty-reply recovery and persistent failures."""

from __future__ import annotations

import json
from typing import Any

from agent.provider import LLMResponse, is_truncated_finish_reason
from core.common.diagnostic_log import current_diagnostic_context
from core.common.error_summary import summarize_exception_for_user


def response_diagnostics(
    response: LLMResponse, *, normalized: str | None, fallback_model: str
) -> dict[str, Any]:
    """Describe emptiness without retaining dialogue, thinking, or credentials."""
    content = response.content or ""
    finish_reason = (response.finish_reason or "unknown").strip().casefold()
    raw_length = response.raw_content_length
    if raw_length is None:
        raw_length = len(content)
    if (normalized or "").strip():
        empty_kind = None
    elif content.strip() or response.raw_content_blank is False:
        empty_kind = "normalization_empty"
    else:
        empty_kind = "whitespace" if raw_length else "raw_empty"
    return {
        "model": (response.model or fallback_model)[:96],
        "stream": response.stream,
        "finish_reason": finish_reason[:32],
        "truncated": is_truncated_finish_reason(response.finish_reason),
        "empty_kind": empty_kind,
        "raw_length": raw_length,
        "content_length": len(content),
        "normalized_length": len(normalized or ""),
        "thinking_length": len(response.thinking or ""),
        "tool_count": len(response.tool_calls),
        "prompt_tokens": response.cache_prompt_tokens,
        "cache_hit_tokens": response.cache_hit_tokens,
        "total_tokens": response.total_tokens,
        "refused": response.refused or finish_reason == "content_filter",
    }


def recovery_diagnostics(
    attempts: list[dict[str, Any]],
    *,
    outcome: str,
    retries: int,
    session: str,
    channel: str,
    iteration: int,
) -> dict[str, Any]:
    """Correlate at most two response snapshots with their owning passive turn."""
    context = current_diagnostic_context()
    return {
        "outcome": outcome,
        "retries": retries,
        "channel": channel[:64],
        "session": (session or context["session"])[:128],
        "turn": context["turn"][:64],
        "iteration": iteration,
        "attempts": attempts[:2],
    }


class EmptyReplyError(RuntimeError):
    """A final reply could not be produced within its single recovery attempt."""

    def __init__(
        self, diagnostics: dict[str, Any], *, request_error: Exception | None = None
    ) -> None:
        if request_error is not None:
            diagnostics = {
                **diagnostics,
                "error_type": type(request_error).__name__[:64],
                "error_summary": summarize_exception_for_user(request_error),
            }
        self.diagnostics = diagnostics
        # Keep response facts on the exception so callers can persist them even
        # when a long provider traceback cannot fit in the global error record.
        super().__init__(
            "模型未产出有效正文。 "
            + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
        )
