"""One-line, credential-scrubbed exception summaries safe to show a user.

A failed chat turn tells the user something generic ("处理消息时出错"); the
desktop can additionally show *why* behind a 「详情」 toggle. That text goes to
the screen, so it is limited to the exception type plus the first line of its
message — never a traceback — with credential-shaped substrings redacted and
the whole thing length-capped.
"""

from __future__ import annotations

import re

from core.common.llm_output_log import redact_secrets

_SUMMARY_MAX_CHARS = 300

# Credentials passed as URL query parameters (e.g. Gemini's `?key=...`), which
# the key/value patterns in `redact_secrets` do not name.
_QUERY_SECRET_PATTERN = re.compile(
    r"(?i)([?&](?:key|api[_-]?key|access[_-]?token|token|signature)=)[^&\s\"']+"
)


def summarize_exception_for_user(
    exc: BaseException, *, limit: int = _SUMMARY_MAX_CHARS
) -> str:
    """Returns `Type: first line of message`, scrubbed and capped at `limit` chars."""
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    message = " ".join(lines[0].split()) if lines else ""
    summary = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    summary = _QUERY_SECRET_PATTERN.sub(r"\1***REDACTED***", redact_secrets(summary))
    if len(summary) <= limit:
        return summary
    return f"{summary[: limit - 1]}…"


__all__ = ["summarize_exception_for_user"]
