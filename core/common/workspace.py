from __future__ import annotations

from pathlib import Path

def resolve_default_workspace(home: Path | None = None) -> Path:
    """Resolve the canonical Shiori workspace path."""

    home_dir = home or Path.home()
    return home_dir / ".shiori" / "workspace"


def resolve_ncatbot_dir(home: Path | None = None) -> Path:
    """Resolve the canonical NcatBot runtime directory."""

    home_dir = home or Path.home()
    return home_dir / ".shiori" / "ncatbot"
