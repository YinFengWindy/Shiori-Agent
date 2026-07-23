from __future__ import annotations

import re

OBSERVATION_RISK_SIGNALS = frozenset(
    {
        "sensitive",
        "credential",
        "payment",
        "destructive",
        "security_warning",
        "prompt_injection",
    }
)

_SENSITIVE_TEXT = re.compile(
    r"(?i)(password|passwd|otp|one[- ]?time|api[_ -]?key|secret|验证码|密码|密钥|"
    r"https?://|[a-z]:\\|\\\\[^\\\s]+\\|/(?:[^/\s]+/)+|"
    r"[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:sk|ghp|github_pat)[-_][a-z0-9_-]{8,}|"
    r"\b[xy]\s*[:=]\s*\d+|\(\s*\d{1,5}\s*,\s*\d{1,5}\s*\))"
)


def contains_sensitive_observation_text(value: object) -> bool:
    """Returns whether a model-derived value contains text forbidden from output."""

    return bool(_SENSITIVE_TEXT.search(str(value or "")))


def safe_observation_text(value: object, *, limit: int) -> str:
    """Normalizes one model-derived string and drops sensitive literal content."""

    text = " ".join(str(value or "").split()).strip()
    if not text or contains_sensitive_observation_text(text):
        return ""
    return text[:limit]
