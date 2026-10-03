"""Normalize working state and audit its bounded output without retaining text."""

from dataclasses import dataclass, replace
import json

from agent.prompting.output_usage import OutputTokenUsage
from agent.prompting.token_estimate import estimate_tokens

SUMMARY_TOKEN_LIMIT = 2000
SUMMARY_FIELDS = (
    "tasks",
    "constraints",
    "decisions",
    "unfinished",
    "tool_state",
    "entities",
)


@dataclass(frozen=True)
class SummaryAttempt:
    """Safe counts and outcomes for one request, never summary text or source IDs."""

    limit: int
    batch: int = 1
    rewrite: int = 0
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    provider_output_tokens: int | None = None
    local_tokens: int | None = None
    counted_tokens: int | None = None
    source: str = "unavailable"
    fallback_reason: str = ""
    source_count: int = 0
    outcome: str = "invalid"


@dataclass(frozen=True)
class WorkingSummary:
    """Validated replacement, deduplicated provenance and request-local diagnostics."""

    content: str
    source_ids: tuple[str, ...]
    diagnostics: tuple[SummaryAttempt, ...] = ()


class SummaryGenerationError(ValueError):
    """Preserve safe diagnostics even when no summary may be committed."""

    def __init__(self, message: str, diagnostics: tuple[SummaryAttempt, ...]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


class SummaryTooLong(SummaryGenerationError):
    """Only a complete, structurally valid summary is eligible for shortening."""

    def __init__(self, summary: WorkingSummary) -> None:
        self.summary = summary
        count = summary.diagnostics[-1]
        label = (
            "上游输出上界"
            if count.source == "provider_output_upper_bound"
            else "本地估算"
        )
        super().__init__(
            f"工作摘要超过 {count.limit} token 上限（本次 {count.counted_tokens}，口径：{label}）",
            summary.diagnostics,
        )


def validate_summary_limit(limit: int) -> None:
    """Reject non-integer or non-positive limits at every configuration boundary."""
    if type(limit) is not int or limit <= 0:
        raise ValueError("工作摘要 token 上限必须是正整数")


def summary_attempt(
    limit: int, usage: OutputTokenUsage | None, **changes
) -> SummaryAttempt:
    """Capture validated provider counts before parsing or truncation checks."""
    return SummaryAttempt(
        limit=limit,
        completion_tokens=usage.completion_tokens if usage else None,
        reasoning_tokens=usage.reasoning_tokens if usage else None,
        provider_output_tokens=usage.visible_tokens if usage else None,
        fallback_reason=(
            usage.unavailable_reason if usage else "missing_completion_usage"
        ),
        **changes,
    )


def normalize_summary(
    content: str, allowed_ids: set[str], attempt: SummaryAttempt
) -> WorkingSummary:
    """Check structure/provenance first, then count only the normalized working state."""
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("工作摘要必须为 JSON 对象")
    required = (*SUMMARY_FIELDS, "source_message_ids")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"工作摘要缺少字段：{', '.join(missing)}")
    if any(not isinstance(payload[key], str) for key in SUMMARY_FIELDS):
        raise ValueError("工作摘要状态字段必须为文本")
    ids = payload["source_message_ids"]
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(value, str) or value not in allowed_ids for value in ids)
    ):
        raise ValueError("工作摘要来源消息无效")
    source_ids = tuple(dict.fromkeys(ids))
    normalized = json.dumps(
        {key: payload[key] for key in SUMMARY_FIELDS}
        | {"source_message_ids": source_ids},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    local_tokens = estimate_tokens(normalized)
    tokens = attempt.provider_output_tokens
    source = "provider_output_upper_bound"
    reason = attempt.fallback_reason
    # Raw usage bounds the normalized projection, but cannot measure a smaller
    # projection exactly. Do not charge removed metadata or duplicate source IDs.
    projected = len(payload) != len(required) or len(source_ids) != len(ids)
    if tokens is None or (projected and tokens > attempt.limit):
        tokens, source = local_tokens, "local_normalized_estimate"
        reason = (
            "normalized_projection"
            if projected and attempt.provider_output_tokens is not None
            else reason
        )
    attempt = replace(
        attempt,
        local_tokens=local_tokens,
        counted_tokens=tokens,
        source=source,
        fallback_reason=reason,
        source_count=len(source_ids),
        outcome="oversized" if tokens > attempt.limit else "accepted",
    )
    summary = WorkingSummary(normalized, source_ids, (attempt,))
    if tokens > attempt.limit:
        raise SummaryTooLong(summary)
    return summary
