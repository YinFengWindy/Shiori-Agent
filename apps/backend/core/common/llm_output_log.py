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

# Credential-shaped key names covered by the two key/value patterns below.
# `fetch_role_mood` - this helper's main caller - always requests
# `response_format={"type": "json_object"}`, so a leaked credential most
# often shows up JSON-quoted (`"api_key": "..."`), not bare `k=v`; both
# shapes are covered, see the patterns below.
# The separator class includes a literal space: a model echoing a credential
# in prose writes "api key: ..." as readily as "api_key=...", and the spaced
# form leaked past an earlier version of this pattern.
_KEY_NAMES = (
    r"api[_\- ]?key|access[_\- ]?token|refresh[_\- ]?token|client[_\- ]?secret"
    r"|secret|password|authorization|token"
)

# Best-effort scrub of credential-shaped substrings before raw model output
# ever reaches a log line. Model output does not normally contain our own
# credentials, but this is a cheap backstop against the model echoing back
# something that looks like one (e.g. copied from tool output in context).
#
# Order matters: the Bearer/sk- patterns must run *before* the generic bare
# key/value pattern. `"Authorization: Bearer <token>"` is itself a bare
# `key: value` shape whose "value" (`Bearer`) is only 6 characters and ends
# at the first space - if the generic pattern ran first, it would redact
# just the word "Bearer" and leave the actual token sitting right after it,
# unredacted. Running the Bearer pattern first consumes the whole
# "Bearer <token>" span so nothing is left for the generic pattern to
# mis-truncate at.
_SECRET_LOG_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # JSON-quoted key/value, e.g. {"api_key": "AIzaSy..."} - only the value
    # between the quotes is replaced. No length cap here: the closing quote
    # is already a safe, unambiguous stopping point (unlike the bare
    # pattern below, there is no risk of running past the credential into
    # unrelated text), and the replacement text is fixed-length regardless
    # of how long the original value was, so an uncapped match can't make
    # the logged line any longer - only shorter.
    (
        re.compile(r'(?i)("(?:' + _KEY_NAMES + r')"\s*:\s*")[^"]+(")'),
        r"\1***REDACTED***\2",
    ),
    # "Authorization: Bearer <token>" / bare "Bearer <token>".
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{8,120}"), "Bearer ***REDACTED***"),
    # sk-... style keys (OpenAI/Anthropic/DeepSeek-shaped), standalone.
    (re.compile(r"sk-[A-Za-z0-9_-]{10,120}"), "sk-***REDACTED***"),
    # Bare key=value / key: value (unquoted), e.g. api_key=AIzaSy... or
    # password: hunter2. Value is capped at 120 chars for the same reason
    # as the JSON pattern above, and additionally stops at the first
    # whitespace/comma/quote/brace so it can't run past the credential into
    # unrelated trailing text (e.g. Chinese dialogue that happens to follow
    # a colon).
    (
        re.compile(r"(?i)\b(" + _KEY_NAMES + r')(\s*[:=]\s*)[^\s,"\'{}]{6,120}'),
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
