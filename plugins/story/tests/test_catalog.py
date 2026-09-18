"""The catalog migrates the complete Story database family before opening it."""

import sqlite3

from plugins.story.backend.catalog import StoryCatalog


def test_unopened_story_images_are_copied_before_catalog_returns(tmp_path):
    source = tmp_path / "private_runtime/novelai/old.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"archived CG")
    database = tmp_path / "stories/archived/story.db"
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
    catalog = StoryCatalog(tmp_path)
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


def test_catalog_migrates_nested_databases_with_committed_wal(tmp_path):
    old = tmp_path / "stories"
    story = old / "story-1/story.db"
    story.parent.mkdir(parents=True)
    connection = sqlite3.connect(story)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE saved_content(value TEXT)")
        connection.execute("INSERT INTO saved_content VALUES ('story survives')")
        connection.commit()
        catalog = StoryCatalog(tmp_path)
        try:
            copied = sqlite3.connect(catalog.root / "story-1/story.db")
            try:
                assert copied.execute("SELECT value FROM saved_content").fetchone() == (
                    "story survives",
                )
            finally:
                copied.close()
            assert catalog.root == tmp_path / "plugin-data/story/stories"
            assert story.is_file()
        finally:
            catalog.close()
    finally:
        connection.close()
