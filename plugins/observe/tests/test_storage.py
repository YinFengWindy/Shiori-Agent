"""Observe migration must leave another plugin's colocated legacy log alone."""

import sqlite3

from plugins.observe.backend.storage import database_path, prepare_storage


def test_migrates_only_owned_database_and_retention_marker(tmp_path):
    old = tmp_path / "observe"
    old.mkdir()
    connection = sqlite3.connect(old / "observe.db")
    try:
        connection.execute("CREATE TABLE saved(value TEXT)")
        connection.execute("INSERT INTO saved VALUES ('telemetry')")
        connection.commit()
    finally:
        connection.close()
    (old / ".last_cleanup").write_text("ok", encoding="utf-8")
    (old / "recall_inspector.jsonl").write_text("memory log", encoding="utf-8")
    target = prepare_storage(tmp_path)
    assert target == database_path(tmp_path)
    assert (target.parent / ".last_cleanup").read_text(encoding="utf-8") == "ok"
    assert (old / "recall_inspector.jsonl").read_text(encoding="utf-8") == "memory log"
    assert not (target.parent / "recall_inspector.jsonl").exists()
    copied = sqlite3.connect(target)
    try:
        assert copied.execute("SELECT value FROM saved").fetchone() == ("telemetry",)
    finally:
        copied.close()
