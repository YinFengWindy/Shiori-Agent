"""Formatting helper for logging raw LLM output on a parse/format failure.

This is the one place output-logging formatting lives: every call site that
logs raw model output on a parse failure (`agent.provider`'s tool-call
argument parsing, `agent.core.reply_completion.fetch_role_mood`,
`agent.core.response_parser`) imports `summarize_llm_output_for_log` from
here instead of re-implementing truncation/redaction locally.

Lives under `core/common/` - not `agent/provider.py` - specifically so
`agent/core/response_parser.py` can depend on it too: that module is loaded
standalone via `importlib` in its test suite
(`tests/backend/agent/core/test_response_parser.py`) to keep it decoupled
from the rest of the `agent` package, but the repository's root
`pytest.ini` puts `apps/backend` on `pythonpath`, so `core.common.*` still
resolves correctly in that standalone-load scenario without dragging in
`agent.provider` or any of its heavier imports.
"""

from __future__ import annotations

import re

_LOG_OUTPUT_MAX_CHARS = 500

# Best-effort scrub of credential-shaped substrings before raw model output
# ever reaches a log line. Model output does not normally contain our own
# credentials, but this is a cheap backstop against the model echoing back
# something that looks like one (e.g. copied from tool output in context).
_SECRET_LOG_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "sk-***REDACTED***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{8,}"), "Bearer ***REDACTED***"),
    (
        re.compile(
            r"(?i)(api[_-]?key|access[_-]?token|secret)(\s*[:=]\s*)([^\s,\"']{6,})"
        ),
        r"\1\2***REDACTED***",
    ),
)


def _redact_secrets(text: str) -> str:
    redacted = text
    for pattern, replacement in _SECRET_LOG_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def summarize_llm_output_for_log(
    content: str | None, *, limit: int = _LOG_OUTPUT_MAX_CHARS
) -> str:
    """Render raw model output for a log line: credential-scrubbed and
    length-capped so a parse/format failure stays diagnosable after the
    fact without risking a log flood or leaking secrets.
    """
    if not content:
        return "<empty>"
    text = _redact_secrets(content)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(+{len(text) - limit} chars)"


__all__ = ["summarize_llm_output_for_log"]
