"""SQLite LIKE helpers for user-entered keyword searches."""

from __future__ import annotations

LIKE_ESCAPE_CLAUSE = "ESCAPE '\\'"
"""Clause to append after every ``LIKE ?`` bound to :func:`like_contains`."""


def like_contains(text: str) -> str:
    """Build a substring LIKE pattern that matches ``text`` literally.

    ``%``, ``_`` and the escape character itself lose their wildcard meaning, so
    the SQL using this pattern must declare ``LIKE ? ESCAPE '\\'``.
    """

    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
