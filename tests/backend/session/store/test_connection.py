"""Opening the session store upgrades stored rows in place."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from session.store import SessionStore


def _write(db: Path, rows: dict[str, dict]) -> None:
    SessionStore(db).close()
    with sqlite3.connect(db) as connection:
        for key, metadata in rows.items():
            connection.execute(
                "INSERT INTO sessions (key, created_at, updated_at, metadata) "
                "VALUES (?, '', '', ?)",
                (key, json.dumps(metadata, ensure_ascii=False)),
            )


def _stored(db: Path) -> dict[str, str]:
    with sqlite3.connect(db) as connection:
        return dict(connection.execute("SELECT key, metadata FROM sessions"))


def test_opening_drops_the_retired_affection_copies_once(tmp_path: Path) -> None:
    db = tmp_path / "sessions.db"
    _write(
        db,
        {
            "role:mira": {
                "role_id": "mira",
                "current_thought": "我在等你。",
                "relationship_snapshot": {"relation_tags": ["亲近"]},
                "loneliness_runtime": {"loneliness_value": 40},
                "affection": {"value": 50},
            },
            "role:yin": {"role_id": "yin", "note": "没有旧键"},
        },
    )
    untouched = _stored(db)["role:yin"]

    SessionStore(db).close()
    first = _stored(db)
    SessionStore(db).close()

    assert json.loads(first["role:mira"]) == {
        "role_id": "mira",
        "current_thought": "我在等你。",
    }
    assert first["role:yin"] == untouched
    assert _stored(db) == first
