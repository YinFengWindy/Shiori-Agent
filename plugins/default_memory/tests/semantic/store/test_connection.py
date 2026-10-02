from __future__ import annotations

import sqlite3
from pathlib import Path

from plugins.default_memory.backend.semantic.store import MemoryStore2


def test_memory_store_runtime_migrates_emotional_weight_column(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE memory_items (
            id            TEXT PRIMARY KEY,
            memory_type   TEXT NOT NULL,
            summary       TEXT NOT NULL,
            content_hash  TEXT NOT NULL,
            embedding     TEXT,
            reinforcement INTEGER NOT NULL DEFAULT 1,
            extra_json    TEXT,
            source_ref    TEXT,
            happened_at   TEXT,
            status        TEXT NOT NULL DEFAULT 'active',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );
        """)
    conn.commit()
    conn.close()

    store = MemoryStore2(db_path)
    try:
        cols = {
            row[1]
            for row in store._db.execute("PRAGMA table_info(memory_items)").fetchall()
        }
        assert "emotional_weight" in cols
    finally:
        store.close()
