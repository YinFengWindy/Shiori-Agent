"""The catalog migrates the complete Story database family before opening it."""

from agent.plugin_host.storage import PluginStorage

import sqlite3

from plugins.story.backend.catalog import StoryCatalog


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
        catalog = StoryCatalog(tmp_path, storage=PluginStorage())
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
