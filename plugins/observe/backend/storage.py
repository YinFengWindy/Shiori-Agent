"""The observe owner's canonical database and retention marker."""

from pathlib import Path

from shiori_sdk.extensions import PrivateStorage


def database_path(workspace: Path) -> Path:
    """Resolve the read-only telemetry path without creating storage."""
    return (workspace / "plugin-data" / "observe") / "observe.db"


def prepare_storage(workspace: Path, storage: PrivateStorage) -> Path:
    """Migrate only observe-owned files before the writer opens its connection."""
    for filename in ("observe.db", ".last_cleanup"):
        storage.migrate_data(
            workspace, "observe", filename, workspace / "observe" / filename
        )
    return database_path(workspace)
