"""Small, local SQLite migrations for the Story bounded context."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

from ._json import dump, load
from .story_time import (
    legacy_story_date,
    legacy_story_time_band,
    normalize_story_date,
    normalize_story_time_band,
)


def migrate_story_timeline(connection: sqlite3.Connection) -> None:
    """Persist a Story date while retaining the five player-facing periods."""

    segment_columns = _table_columns(connection, "segments")
    beat_columns = _table_columns(connection, "beats")
    if not segment_columns:
        return
    has_legacy_segments = "starts_at" in segment_columns
    has_legacy_beats = "effective_at" in beat_columns

    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN")
        if "time_band" not in segment_columns:
            connection.execute("ALTER TABLE segments ADD COLUMN time_band TEXT")
        if "story_date" not in segment_columns:
            connection.execute("ALTER TABLE segments ADD COLUMN story_date TEXT")

        segment_timeline: dict[str, tuple[str, str]] = {}
        segment_rows = connection.execute("SELECT * FROM segments").fetchall()
        for row in segment_rows:
            legacy_start = str(row["starts_at"]) if has_legacy_segments else ""
            fallback_date = _story_created_date(connection, str(row["story_id"]))
            story_date = _safe_story_date(
                str(row["story_date"] or "") if "story_date" in row.keys() else "",
                _safe_legacy_date(legacy_start, fallback_date),
            )
            time_band = _safe_time_band(
                str(row["time_band"] or "") if "time_band" in row.keys() else "",
                _safe_legacy_band(legacy_start, "上午"),
            )
            segment_timeline[str(row["id"])] = (story_date, time_band)
            connection.execute(
                "UPDATE segments SET story_date = ?, time_band = ? WHERE id = ?",
                (story_date, time_band, str(row["id"])),
            )
        if has_legacy_segments:
            connection.execute("ALTER TABLE segments DROP COLUMN starts_at")

        beat_timeline: dict[str, tuple[str, str]] = {}
        beat_query = "SELECT id, payload" + (", effective_at" if has_legacy_beats else "") + " FROM beats"
        for row in connection.execute(beat_query).fetchall():
            payload = load(row["payload"], {})
            legacy_value = str(row["effective_at"]) if has_legacy_beats else ""
            segment_date, segment_band = segment_timeline.get(
                str(payload.get("segment_id") or ""), ("1970-01-01", "上午")
            )
            story_date = _safe_story_date(
                str(payload.get("story_date") or payload.get("storyDate") or ""),
                _safe_legacy_date(legacy_value, segment_date),
            )
            time_band = _safe_time_band(
                str(payload.get("time_band") or payload.get("timeBand") or ""),
                _safe_legacy_band(legacy_value, segment_band),
            )
            payload["story_date"] = story_date
            payload["time_band"] = time_band
            payload.pop("storyDate", None)
            payload.pop("effective_at", None)
            payload.pop("effectiveAt", None)
            beat_id = str(row["id"])
            beat_timeline[beat_id] = (story_date, time_band)
            connection.execute(
                "UPDATE beats SET payload = ? WHERE id = ?", (dump(payload), beat_id)
            )
        if has_legacy_beats:
            connection.execute("ALTER TABLE beats DROP COLUMN effective_at")
        for sequence, payload in _clean_outbox_payloads(connection, beat_timeline):
            connection.execute(
                "UPDATE outbox SET payload = ? WHERE sequence = ?", (payload, sequence)
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_story_beats_sequence "
            "ON beats(story_id, sequence)"
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def migrate_legacy_story_time(connection: sqlite3.Connection) -> None:
    """Compatibility entry point for callers of the former timestamp migration."""

    migrate_story_timeline(connection)


def migrate_story_resources(connection: sqlite3.Connection) -> None:
    """Add visual type metadata and give legacy Stories a background fallback."""

    resource_columns = _table_columns(connection, "story_resources")
    if "visual_type" not in resource_columns:
        connection.execute(
            "ALTER TABLE story_resources ADD COLUMN visual_type TEXT NOT NULL DEFAULT 'scene'"
        )
        connection.commit()
    if "scene_key" not in resource_columns:
        connection.execute(
            "ALTER TABLE story_resources ADD COLUMN scene_key TEXT NOT NULL DEFAULT ''"
        )
        connection.commit()

    stories = connection.execute("SELECT id FROM stories").fetchall()
    if not stories:
        return
    now = "1970-01-01T00:00:00+00:00"
    connection.executemany(
        """INSERT INTO story_resources
        (id, story_id, kind, visual_type, scene_key, status, path, prompt, source_turn_id,
         sequence, error_code, created_at, updated_at)
        SELECT ?, ?, 'background', 'scene', '', 'failed', NULL, '', NULL, 1,
               'legacy_story_no_background', ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM story_resources WHERE story_id = ? AND kind = 'background'
        )""",
        [
            (f"resource-{uuid4().hex}", str(row[0]), now, now, str(row[0]))
            for row in stories
        ],
    )


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _clean_outbox_payloads(
    connection: sqlite3.Connection,
    beat_timeline: dict[str, tuple[str, str]],
) -> list[tuple[int, str]]:
    cleaned: list[tuple[int, str]] = []
    for row in connection.execute("SELECT sequence, payload FROM outbox").fetchall():
        payload = load(row["payload"], {})
        beat = payload.get("beat")
        if isinstance(beat, dict):
            beat_id = str(beat.get("id") or "")
            story_date, time_band = beat_timeline.get(beat_id, ("", ""))
            legacy_value = str(
                beat.pop("effective_at", None) or beat.pop("effectiveAt", None) or ""
            )
            if not time_band:
                time_band = _safe_legacy_band(legacy_value, "")
            if not story_date:
                story_date = _safe_legacy_date(legacy_value, "")
            if story_date:
                beat["story_date"] = story_date
            if time_band:
                beat["time_band"] = time_band
            beat.pop("storyDate", None)
            beat.pop("effective_at", None)
            beat.pop("effectiveAt", None)
        cleaned.append((int(row["sequence"]), dump(payload)))
    return cleaned


def _story_created_date(connection: sqlite3.Connection, story_id: str) -> str:
    if not _table_columns(connection, "stories"):
        return "1970-01-01"
    row = connection.execute(
        "SELECT created_at FROM stories WHERE id = ?", (story_id,)
    ).fetchone()
    return _safe_legacy_date(str(row["created_at"]) if row else "", "1970-01-01")


def _safe_legacy_date(value: str, fallback: str) -> str:
    if value:
        try:
            return legacy_story_date(value)
        except ValueError:
            pass
    return fallback


def _safe_legacy_band(value: str, fallback: str) -> str:
    if value:
        try:
            return legacy_story_time_band(value)
        except ValueError:
            pass
    return fallback


def _safe_story_date(value: str, fallback: str) -> str:
    if value:
        try:
            return normalize_story_date(value)
        except ValueError:
            pass
    return fallback


def _safe_time_band(value: str, fallback: str) -> str:
    if value:
        try:
            return normalize_story_time_band(value)
        except ValueError:
            pass
    return fallback
