"""Host-owned visibility provenance for the derived recent-context document."""

from __future__ import annotations

import json

from conversation.context_scope import UserContextThreads
from session.maintenance_progress import ownership_key

_PREFIX = "<!-- shiori-recent-context:v1 "
_SUFFIX = " -->"


def stamp_recent_context(content: str, user_threads: UserContextThreads | None) -> str:
    """Bind generated text to the visibility snapshot that supplied its inputs."""
    if user_threads is None:
        return content
    return f"{_PREFIX}{ownership_key(user_threads)}{_SUFFIX}\n{content.strip()}\n"


def visible_recent_context(
    content: str, user_threads: UserContextThreads | None
) -> str:
    """Adopt only a document whose original allowed inputs remain visible.

    Added bindings cannot contaminate an earlier snapshot. Removed bindings or
    changed boundaries invalidate it. Unmarked role documents remain on disk,
    but cannot be assigned a new provenance by reading or refreshing them.
    """
    text = content.lstrip()
    if user_threads is None:
        return "" if text.startswith(_PREFIX) else content
    marker, _, body = text.partition("\n")
    if not marker.startswith(_PREFIX) or not marker.endswith(_SUFFIX):
        return ""
    previous = json.loads(marker[len(_PREFIX) : -len(_SUFFIX)])
    if not isinstance(previous, dict) or any(
        not isinstance(thread, str) or not isinstance(since, str)
        for thread, since in previous.items()
    ):
        raise ValueError("近期语境来源标记无效")
    current = json.loads(ownership_key(user_threads))
    if any(current.get(thread) != since for thread, since in previous.items()):
        return ""
    return body
