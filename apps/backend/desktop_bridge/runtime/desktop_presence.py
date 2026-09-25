"""Bridge handler for desktop presence reports."""

from __future__ import annotations

from typing import Any

from core.desktop_presence import DesktopPresence


def report_desktop_presence(
    presence: DesktopPresence, payload: dict[str, Any]
) -> dict[str, bool]:
    """Stores the host's report; ``present`` must be a real boolean."""
    present = payload.get("present")
    if not isinstance(present, bool):
        raise ValueError("present 必须是布尔值")
    presence.report(present)
    return {"present": presence.is_desktop_present()}
