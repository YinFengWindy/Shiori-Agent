import json
import sqlite3

from story_simulation.schema_migrations import migrate_legacy_story_time
from story_simulation.schema_migrations import migrate_story_resources


def test_migrate_legacy_story_timestamps_to_periods() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE segments (
            id TEXT PRIMARY KEY,
            story_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            starts_at TEXT NOT NULL,
            status TEXT NOT NULL,
            mode TEXT NOT NULL,
            operation TEXT NOT NULL,
            opening_context TEXT NOT NULL,
            runtime_snapshot TEXT NOT NULL
        );
        CREATE TABLE beats (
            id TEXT PRIMARY KEY,
            story_id TEXT NOT NULL,
            segment_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            effective_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE outbox (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL
        );
        INSERT INTO segments VALUES (
            'segment-1', 'story-1', 1, '2026-08-01T09:00:00+08:00',
            'active', 'plot', 'awaiting_player', '{}', '{}'
        );
        INSERT INTO beats VALUES (
            'beat-1', 'story-1', 'segment-1', 'turn-1', 1,
            '2026-08-01T20:00:00+08:00',
            '{"id":"beat-1","effective_at":"2026-08-01T20:00:00+08:00"}',
            '2026-08-01T12:00:00+08:00'
        );
        INSERT INTO outbox(payload) VALUES (
            '{"beat":{"effective_at":"2026-08-01T20:00:00+08:00"}}'
        );
        """
    )

    migrate_legacy_story_time(connection)

    assert {row[1] for row in connection.execute("PRAGMA table_info(segments)")} == {
        "id",
        "story_id",
        "sequence",
        "story_date",
        "time_band",
        "status",
        "mode",
        "operation",
        "opening_context",
        "runtime_snapshot",
    }
    assert "effective_at" not in {
        row[1] for row in connection.execute("PRAGMA table_info(beats)")
    }
    beat_payload = json.loads(connection.execute("SELECT payload FROM beats").fetchone()[0])
    assert beat_payload == {
        "id": "beat-1",
        "story_date": "2026-08-01",
        "time_band": "夜晚",
    }
    outbox_payload = json.loads(connection.execute("SELECT payload FROM outbox").fetchone()[0])
    assert outbox_payload == {
        "beat": {"story_date": "2026-08-01", "time_band": "夜晚"}
    }
    connection.close()


def test_migrate_story_resources_adds_visual_type_to_legacy_table() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE stories (id TEXT PRIMARY KEY);
        CREATE TABLE story_resources (
            id TEXT PRIMARY KEY,
            story_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            path TEXT,
            prompt TEXT NOT NULL,
            source_turn_id TEXT,
            sequence INTEGER NOT NULL,
            error_code TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO stories VALUES ('story-1');
        INSERT INTO story_resources VALUES (
            'resource-1', 'story-1', 'cg', 'ready', 'scene.png', 'old scene', NULL, 1,
            NULL, '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00'
        );
        """
    )

    migrate_story_resources(connection)

    columns = {row[1] for row in connection.execute("PRAGMA table_info(story_resources)")}
    assert "visual_type" in columns
    assert "scene_key" in columns
    assert connection.execute("SELECT visual_type FROM story_resources").fetchone()[0] == "scene"
    assert connection.execute("SELECT scene_key FROM story_resources").fetchone()[0] == ""
    connection.close()
