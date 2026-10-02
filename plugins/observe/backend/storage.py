"""The observe owner's canonical database and retention marker."""

from pathlib import Path

from shiori_sdk.extensions import PrivateStorage
from shiori_sdk.storage import plugin_data_dir


def database_path(workspace: Path) -> Path:
    """Resolve the read-only telemetry path without creating storage."""
    return plugin_data_dir(workspace, "observe") / "observe.db"


def prepare_storage(workspace: Path, storage: PrivateStorage) -> Path:
    """Migrate only observe-owned files before the writer opens its connection."""
    db_path = storage.migrate_data(
        workspace, "observe", "observe.db", workspace / "observe" / "observe.db"
    )
    storage.migrate_data(
        workspace, "observe", ".last_cleanup", workspace / "observe" / ".last_cleanup"
    )
    return db_path
