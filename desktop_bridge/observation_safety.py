from __future__ import annotations

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


def safe_observation_text(value: object, *, limit: int) -> str:
    """Normalizes one model-derived string without redacting screen content."""

    return " ".join(str(value or "").split()).strip()[:limit]
