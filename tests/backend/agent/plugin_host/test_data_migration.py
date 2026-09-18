"""Private artifact migration preserves WAL, conflicts and reset intent."""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from agent.plugin_host.data_migration import migrate_private_data
from infra.persistence.sqlite_lifecycle import open_owned_database


def test_live_old_owner_requires_restart_before_migration(tmp_path):
    source = tmp_path / "old.db"
    connection = open_owned_database(source)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE content(value TEXT)")
    connection.execute("INSERT INTO content VALUES ('last commit')")
    connection.commit()
    with pytest.raises(RuntimeError, match="请重启"):
        migrate_private_data(tmp_path, "demo", "data.db", source)
    connection.close()
    target = migrate_private_data(tmp_path, "demo", "data.db", source)
    copied = sqlite3.connect(target)
    try:
        assert copied.execute("SELECT value FROM content").fetchone() == (
            "last commit",
        )
    finally:
        copied.close()


def test_database_snapshot_includes_uncheckpointed_wal_and_survives_reset(tmp_path):
    source = tmp_path / "old.db"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE content (value TEXT)")
        connection.execute("INSERT INTO content VALUES ('committed in WAL')")
        connection.commit()
        assert Path(str(source) + "-wal").stat().st_size > 0
        target = migrate_private_data(tmp_path, "demo", "data.db", source)
        with sqlite3.connect(target) as migrated:
            assert migrated.execute("SELECT value FROM content").fetchone() == (
                "committed in WAL",
            )
        migrated.close()
        assert source.is_file()
    connection.close()
    target.unlink()
    assert migrate_private_data(tmp_path, "demo", "data.db", source) == target
    assert not target.exists()


def test_conflicting_target_is_never_replaced(tmp_path):
    source = tmp_path / "old.json"
    source.write_text('{"old": true}', encoding="utf-8")
    target = tmp_path / "plugin-data/demo/data.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"new": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="目标已存在"):
        migrate_private_data(tmp_path, "demo", "data.json", source)
    assert json.loads(source.read_text(encoding="utf-8")) == {"old": True}
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}


def test_failed_publish_preserves_source_and_retries(tmp_path, monkeypatch):
    source = tmp_path / "old"
    source.mkdir()
    (source / "asset.png").write_bytes(b"asset")
    original = Path.rename

    def fail(path, target):
        raise OSError("disk unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", fail)
        with pytest.raises(OSError, match="disk unavailable"):
            migrate_private_data(tmp_path, "demo", "assets", source)
    assert (source / "asset.png").read_bytes() == b"asset"
    assert Path.rename == original
    target = migrate_private_data(tmp_path, "demo", "assets", source)
    assert (target / "asset.png").read_bytes() == b"asset"
    shutil.rmtree(source)
    assert migrate_private_data(tmp_path, "demo", "assets", source) == target


def test_missing_source_does_not_create_an_empty_database(tmp_path):
    target = migrate_private_data(tmp_path, "demo", "data.db", tmp_path / "missing.db")
    assert not target.exists()
