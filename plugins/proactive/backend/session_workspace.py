"""The workspace and session surface a proactive loop reads."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class SessionWorkspace(Protocol):
    """Workspace root and role session keys."""

    workspace: Path

    def role_session_key(self, role_id: str) -> str:
        """The shared session key of ``role_id``."""
        ...
