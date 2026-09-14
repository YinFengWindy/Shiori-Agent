"""Connection ownership when schema initialization fails."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from plugins.observe.backend import db


def test_schema_failure_closes_connection_and_preserves_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = sqlite3.connect(tmp_path / "observe.db")

    def connect(*args: Any, **kwargs: Any):
        return conn

    monkeypatch.setattr(db.sqlite3, "connect", connect)
    monkeypatch.setattr(db, "_SCHEMA_SQL", "INVALID SCHEMA")
    try:
        with pytest.raises(sqlite3.OperationalError, match='near "INVALID"'):
            _ = db.open_db(tmp_path / "observe.db")
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            _ = conn.execute("SELECT 1")
    finally:
        conn.close()
