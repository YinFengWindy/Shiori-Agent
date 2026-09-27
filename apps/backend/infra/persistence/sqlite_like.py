"""SQLite LIKE helpers for user-entered keyword searches."""

from __future__ import annotations

LIKE_ESCAPE_CLAUSE = "ESCAPE '\\'"
"""Clause to append after every ``LIKE ?`` bound to a pattern built here."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_contains(text: str) -> str:
    """Build a substring LIKE pattern that matches ``text`` literally.

    ``%``, ``_`` and the escape character itself lose their wildcard meaning, so
    the SQL using this pattern must declare ``LIKE ? ESCAPE '\\'``.
    """

    return f"%{_escape(text)}%"


def like_prefix(text: str) -> str:
    """Build a prefix LIKE pattern that matches rows starting with ``text`` literally.

    Same escaping contract as :func:`like_contains`.
    """

    return f"{_escape(text)}%"
