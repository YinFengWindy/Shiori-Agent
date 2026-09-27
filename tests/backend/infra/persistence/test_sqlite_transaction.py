"""One explicit transaction wraps DDL and commits once or rolls back entirely."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from infra.persistence.sqlite_transaction import immediate_transaction


def test_ddl_block_commits_once(tmp_path: Path) -> None:
    traced: list[str] = []
    with closing(sqlite3.connect(tmp_path / "db.sqlite")) as conn:
        conn.set_trace_callback(traced.append)
        with immediate_transaction(conn):
            conn.execute("CREATE TABLE a (x)")
            conn.execute("ALTER TABLE a ADD COLUMN y")
            assert conn.in_transaction
        assert not conn.in_transaction

    assert traced == [
        "BEGIN IMMEDIATE",
        "CREATE TABLE a (x)",
        "ALTER TABLE a ADD COLUMN y",
        "COMMIT",
    ]


def test_failure_rolls_back_every_ddl_statement(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    with closing(sqlite3.connect(db_path)) as conn:
        with pytest.raises(RuntimeError, match="boom"):
            with immediate_transaction(conn):
                conn.execute("CREATE TABLE a (x)")
                conn.execute("CREATE INDEX idx_a ON a(x)")
                raise RuntimeError("boom")
        assert not conn.in_transaction

    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []
