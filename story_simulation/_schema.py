"""SQLite schema owned by the Story bounded context."""

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    background TEXT NOT NULL,
    role_snapshot TEXT NOT NULL,
    player_profile TEXT NOT NULL,
    status TEXT NOT NULL,
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    time_band TEXT NOT NULL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    operation TEXT NOT NULL,
    opening_context TEXT NOT NULL,
    runtime_snapshot TEXT NOT NULL,
    UNIQUE(story_id, sequence)
);

CREATE TABLE IF NOT EXISTS turns (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    input_text TEXT NOT NULL,
    status TEXT NOT NULL,
    active_attempt_id TEXT,
    committed_beat_ids TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_requests (
    request_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    payload_hash TEXT NOT NULL,
    turn_id TEXT NOT NULL UNIQUE REFERENCES turns(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    failure_category TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS beats (
    id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    turn_id TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    payload TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE(story_id, sequence)
);

CREATE TABLE IF NOT EXISTS cues (
    id TEXT PRIMARY KEY,
    beat_id TEXT NOT NULL UNIQUE REFERENCES beats(id) ON DELETE CASCADE,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
    request_id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    story_id TEXT NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_story_turns_history
ON turns(story_id, created_at, id);

CREATE INDEX IF NOT EXISTS ix_story_beats_sequence
ON beats(story_id, sequence);
"""
