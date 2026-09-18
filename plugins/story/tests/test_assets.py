"""Adopted CG belongs to Story after NovelAI deletes its original."""

import sqlite3
from pathlib import Path

from plugins.story.backend.assets import adopt_existing_images, adopt_image


def test_adopt_image_and_legacy_rows_survive_source_deletion(tmp_path: Path):
    source = tmp_path / "novelai/output.png"
    source.parent.mkdir()
    source.write_bytes(b"CG")
    database = tmp_path / "story/story.db"
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("CREATE TABLE story_resources(id TEXT, path TEXT)")
        connection.execute(
            "INSERT INTO story_resources VALUES ('cg', ?)", (str(source),)
        )
        adopt_existing_images(connection, database)
        path = connection.execute("SELECT path FROM story_resources").fetchone()[0]
        assert path == adopt_image(database, str(source))
        source.unlink()
        assert Path(path).read_bytes() == b"CG"
        adopt_existing_images(connection, database)
    finally:
        connection.close()
