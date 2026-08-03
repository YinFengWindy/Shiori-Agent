"""Small, local SQLite migrations for the Story bounded context."""

from __future__ import annotations

import sqlite3

from ._json import dump, load
from .story_time import legacy_story_time_band


def migrate_legacy_story_time(connection: sqlite3.Connection) -> None:
    """Convert timestamp-based Story databases to the five-period model."""

    segment_columns = _table_columns(connection, "segments")
    beat_columns = _table_columns(connection, "beats")
    has_legacy_segments = "starts_at" in segment_columns
    has_legacy_beats = "effective_at" in beat_columns
    if not has_legacy_segments and not has_legacy_beats:
        return

    segment_bands: dict[str, str] = {}
    if has_legacy_segments:
        for row in connection.execute("SELECT id, starts_at FROM segments").fetchall():
            segment_bands[str(row["id"])] = legacy_story_time_band(str(row["starts_at"]))

    beat_payloads: list[tuple[str, str]] = []
    if has_legacy_beats:
        for row in connection.execute(
            "SELECT id, effective_at, payload FROM beats"
        ).fetchall():
            payload = load(row["payload"], {})
            payload["time_band"] = legacy_story_time_band(str(row["effective_at"]))
            payload.pop("effective_at", None)
            payload.pop("effectiveAt", None)
            beat_payloads.append((str(row["id"]), dump(payload)))

    outbox_payloads = _clean_outbox_payloads(connection)
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN")
        if has_legacy_segments:
            if "time_band" not in segment_columns:
                connection.execute("ALTER TABLE segments ADD COLUMN time_band TEXT")
            connection.executemany(
                "UPDATE segments SET time_band = ? WHERE id = ?",
                [(band, segment_id) for segment_id, band in segment_bands.items()],
            )
            connection.execute("ALTER TABLE segments DROP COLUMN starts_at")
        for beat_id, payload in beat_payloads:
            connection.execute(
                "UPDATE beats SET payload = ? WHERE id = ?", (payload, beat_id)
            )
        if has_legacy_beats:
            connection.execute("ALTER TABLE beats DROP COLUMN effective_at")
        for sequence, payload in outbox_payloads:
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


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _clean_outbox_payloads(
    connection: sqlite3.Connection,
) -> list[tuple[int, str]]:
    cleaned: list[tuple[int, str]] = []
    for row in connection.execute("SELECT sequence, payload FROM outbox").fetchall():
        payload = load(row["payload"], {})
        beat = payload.get("beat")
        if isinstance(beat, dict):
            legacy_value = beat.pop("effective_at", None) or beat.pop("effectiveAt", None)
            if "time_band" not in beat and legacy_value:
                beat["time_band"] = legacy_story_time_band(str(legacy_value))
        cleaned.append((int(row["sequence"]), dump(payload)))
    return cleaned
