"""UTC timestamps for proactive state. Copied from the host time helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time, with tzinfo."""
    return datetime.now(timezone.utc)


def parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp.

    A trailing ``Z`` is accepted. A naive value is treated as UTC. A value
    that does not parse is ``None``.
    """
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
