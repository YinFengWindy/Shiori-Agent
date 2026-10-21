"""The observe owner's canonical database path."""

from pathlib import Path

from shiori_sdk.storage import plugin_data_dir


def database_path(workspace: Path) -> Path:
    """Resolve the telemetry database path without creating storage."""
    return plugin_data_dir(workspace, "observe") / "observe.db"
