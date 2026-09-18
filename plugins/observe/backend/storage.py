"""The observe owner's canonical database and retention marker."""

from pathlib import Path

from agent.plugin_host.data_migration import migrate_private_data
from agent.plugin_host.plugin_data import plugin_data_dir


def database_path(workspace: Path) -> Path:
    """Resolve the read-only telemetry path without creating storage."""
    return plugin_data_dir(workspace, "observe") / "observe.db"


def prepare_storage(workspace: Path) -> Path:
    """Migrate only observe-owned files before the writer opens its connection."""
    for filename in ("observe.db", ".last_cleanup"):
        migrate_private_data(
            workspace, "observe", filename, workspace / "observe" / filename
        )
    return database_path(workspace)
