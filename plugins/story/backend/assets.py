"""Story-owned image copies, independent of the generating plugin's lifetime."""

import sqlite3
from pathlib import Path

from infra.persistence.owned_assets import copy_owned_asset


def adopt_image(database_path: Path, value: str, workspace: Path | None = None) -> str:
    """Preserve an available resource beside its Story database."""
    source = Path(value)
    if not source.is_absolute():
        source = (workspace or database_path.parent) / source
    if source.resolve().is_relative_to((database_path.parent / "assets").resolve()):
        return str(source)
    # An already missing legacy resource stays diagnosable by its original path;
    # moving the database must not erase the rest of the readable Story.
    if not source.is_file():
        return value
    return str(copy_owned_asset(source, database_path.parent / "assets"))


def adopt_existing_images(
    connection: sqlite3.Connection, database_path: Path, workspace: Path | None = None
) -> None:
    """Copy resources first, then publish all replacement paths in one commit."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        rows = connection.execute(
            "SELECT id, path FROM story_resources WHERE path IS NOT NULL"
        ).fetchall()
        updates = []
        for row in rows:
            path = adopt_image(database_path, row["path"], workspace)
            if path != row["path"]:
                updates.append((path, row["id"]))
        connection.executemany(
            "UPDATE story_resources SET path = ? WHERE id = ?", updates
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def adopt_library_images(root: Path, workspace: Path) -> None:
    """Normalize archived and unopened Story references before exposing the catalog."""
    from contextlib import closing

    for database in root.glob("*/story.db"):
        with closing(sqlite3.connect(database, isolation_level=None)) as connection:
            connection.row_factory = sqlite3.Row
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'story_resources'"
            ).fetchone():
                adopt_existing_images(connection, database, workspace)
