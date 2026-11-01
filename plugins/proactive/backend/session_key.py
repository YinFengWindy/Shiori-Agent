"""Role session keys and the session surface a proactive loop reads."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

ROLE_SESSION_PREFIX = "role:"


def role_session_key(role_id: str) -> str:
    """The shared session key of ``role_id``."""
    clean_role_id = str(role_id).strip()
    if not clean_role_id:
        raise ValueError("role_id 不能为空")
    return f"{ROLE_SESSION_PREFIX}{clean_role_id}"


def role_id_from_session_key(key: str) -> str:
    """The role that owns ``key``, or ``""`` when ``key`` is not a role session."""
    clean_key = str(key or "").strip()
    if not clean_key.startswith(ROLE_SESSION_PREFIX):
        return ""
    return clean_key.removeprefix(ROLE_SESSION_PREFIX).strip()


class SessionWorkspace(Protocol):
    """Workspace root and role session keys. A host ``SessionManager`` satisfies this."""

    workspace: Path

    def role_session_key(self, role_id: str) -> str:
        """The shared session key of ``role_id``."""
        ...
