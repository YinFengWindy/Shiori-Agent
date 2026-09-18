"""Media ownership survives plugin data deletion and preserves provenance."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import session.media_assets as media_assets
from session.media_assets import (
    adopt_persisted_media,
    original_media_path,
    preserve_media,
)


def test_startup_migration_serializes_media_updates_and_does_not_reapply(
    tmp_path, monkeypatch
):
    database = tmp_path / "sessions.db"
    source = tmp_path / "old.png"
    source.write_bytes(b"image")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    other = sqlite3.connect(database, timeout=0)
    other.row_factory = sqlite3.Row
    original = media_assets.preserve_media
    try:
        connection.execute("CREATE TABLE messages(id TEXT, media TEXT)")
        connection.execute(
            "INSERT INTO messages VALUES ('m', ?)", (json.dumps([str(source)]),)
        )
        connection.commit()

        def blocked_update(workspace, paths):
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("UPDATE messages SET media = '[]'")
            other.rollback()
            return original(workspace, paths)

        monkeypatch.setattr(media_assets, "preserve_media", blocked_update)
        adopt_persisted_media(connection, tmp_path)
        other.execute("UPDATE messages SET media = '[]'")
        other.commit()
        adopt_persisted_media(other, tmp_path)
        assert other.execute("SELECT media FROM messages").fetchone()[0] == "[]"
    finally:
        connection.close()
        other.close()


def test_remote_and_missing_references_remain_diagnosable(tmp_path):
    paths = ["https://example.invalid/image.png", str(tmp_path / "missing.png")]
    assert preserve_media(tmp_path, paths) == paths


def test_non_image_attachments_are_not_copied(tmp_path):
    for name in ("document.txt", "voice.mp3", "movie.mp4"):
        source = tmp_path / name
        source.write_bytes(b"attachment")
        assert preserve_media(tmp_path, [str(source)]) == [str(source)]
    assert not (tmp_path / "sessions/media").exists()


def test_concurrent_sessions_adopt_one_source_without_metadata_races(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(b"shared source")
    with ThreadPoolExecutor(max_workers=4) as pool:
        copies = list(
            pool.map(lambda _: preserve_media(tmp_path, [str(source)])[0], range(12))
        )
    assert len(set(copies)) == 1
    assert original_media_path(tmp_path, copies[0]) == str(source)


def test_local_asset_is_copied_once_and_survives_source_removal(tmp_path: Path):
    source = tmp_path / "plugin-data/novelai/image.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"generated image")
    copied = preserve_media(tmp_path, [str(source)])[0]
    assert copied != str(source)
    assert original_media_path(tmp_path, copied) == str(source)
    source.unlink()
    assert Path(copied).read_bytes() == b"generated image"
    assert preserve_media(tmp_path, [copied]) == [copied]


def test_existing_message_references_publish_after_copy(tmp_path: Path):
    source = tmp_path / "legacy.png"
    source.write_bytes(b"old image")
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("CREATE TABLE messages(id TEXT, media TEXT)")
        connection.execute(
            "INSERT INTO messages VALUES ('message', ?)", (json.dumps([str(source)]),)
        )
        connection.commit()
        adopt_persisted_media(connection, tmp_path)
        media = json.loads(
            connection.execute("SELECT media FROM messages").fetchone()[0]
        )
        assert Path(media[0]).read_bytes() == b"old image"
        assert media != [str(source)]
    finally:
        connection.close()
