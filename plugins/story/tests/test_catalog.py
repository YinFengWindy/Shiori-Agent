"""The catalog migrates the complete Story database family before opening it."""

from shiori_sdk.testing.memory import FakeMemoryStorage

import sqlite3

from plugins.story.backend.catalog import StoryCatalog


def test_unopened_story_images_are_copied_before_catalog_returns(tmp_path):
    source = tmp_path / "private_runtime/novelai/old.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"archived CG")
    database = tmp_path / "plugin-data/story/stories/archived/story.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE story_resources(id TEXT, path TEXT)")
        connection.execute(
            "INSERT INTO story_resources VALUES ('cg', ?)",
            ("private_runtime/novelai/old.png",),
        )
        connection.commit()
    finally:
        connection.close()
    catalog = StoryCatalog(tmp_path, storage=FakeMemoryStorage())
    copied = sqlite3.connect(catalog.root / "archived/story.db")
    try:
        from pathlib import Path

        image = Path(copied.execute("SELECT path FROM story_resources").fetchone()[0])
        source.unlink()
        assert image.read_bytes() == b"archived CG"
        assert image.is_relative_to(catalog.root / "archived/assets")
    finally:
        copied.close()
        catalog.close()


def test_catalog_opens_under_the_root_returned_by_storage_migration(tmp_path):
    """The legacy ``stories`` directory is handed to the storage owner once."""
    selected = tmp_path / "selected-owner-root"
    requests = []

    class Storage(FakeMemoryStorage):
        def migrate_data(self, workspace, plugin_id, name, source):
            requests.append((workspace, plugin_id, name, source))
            return selected

    catalog = StoryCatalog(tmp_path, storage=Storage())
    try:
        assert requests == [(tmp_path, "story", "stories", tmp_path / "stories")]
        assert catalog.root == selected
        assert catalog.db_path == selected / "catalog.db"
        assert catalog.db_path.is_file()
    finally:
        catalog.close()
