"""Bounded, credential-scrubbed rendering of raw model output for host logs."""

from __future__ import annotations

from shiori_sdk.redaction import redact_secrets

_LOG_OUTPUT_MAX_CHARS = 500


def summarize_llm_output_for_log(
    content: str | None, *, limit: int = _LOG_OUTPUT_MAX_CHARS
) -> str:
    """Render raw model output for a log line: credential-scrubbed and
    length-capped so a parse/format failure stays diagnosable after the
    fact without risking a log flood or leaking secrets.
    """
    if not content:
        return "<empty>"
    text = redact_secrets(content)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(+{len(text) - limit} chars)"
