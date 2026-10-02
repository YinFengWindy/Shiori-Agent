"""Pure timestamp and portable relative-path values shared by host and plugins."""

from datetime import datetime


def now_iso() -> str:
    """Return the current local timestamp including its UTC offset."""
    return datetime.now().astimezone().isoformat()


def normalize_rel_path(path: str | None) -> str | None:
    """Normalize persisted relative paths to forward slashes, preserving absence."""
    return path.replace("\\", "/") if path else None
