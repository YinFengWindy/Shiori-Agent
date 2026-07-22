"""SQLite schema owned by the persistent world repository."""

SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS world_drafts (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    template_snapshot TEXT NOT NULL,
    current_time TEXT NOT NULL,
    revision INTEGER NOT NULL,
    active_oc_id TEXT,
    parent_world_id TEXT,
    fork_event_id TEXT,
    random_state TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS role_snapshots (
    id TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    PRIMARY KEY (world_id, id)
);

CREATE TABLE IF NOT EXISTS residents (
    id TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    PRIMARY KEY (world_id, id)
);

CREATE TABLE IF NOT EXISTS player_ocs (
    id TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (world_id, id)
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    dependencies TEXT NOT NULL,
    request_id TEXT NOT NULL,
    committed_revision INTEGER NOT NULL,
    is_backfill INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (world_id, id),
    UNIQUE (world_id, sequence)
);

CREATE INDEX IF NOT EXISTS ix_world_events_effective
ON timeline_events(world_id, effective_at, sequence);

CREATE TABLE IF NOT EXISTS projections (
    world_id TEXT PRIMARY KEY REFERENCES worlds(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    cognition TEXT NOT NULL,
    invalid_after TEXT
);

CREATE TABLE IF NOT EXISTS projection_history (
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    cognition TEXT NOT NULL,
    invalid_after TEXT,
    PRIMARY KEY (world_id, revision)
);

CREATE TABLE IF NOT EXISTS barriers (
    id TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    effective_at TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (world_id, id)
);

CREATE INDEX IF NOT EXISTS ix_world_barriers_pending
ON barriers(world_id, status, effective_at);

CREATE TABLE IF NOT EXISTS scene_threads (
    id TEXT NOT NULL,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    PRIMARY KEY (world_id, id)
);

CREATE TABLE IF NOT EXISTS world_runs (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    starting_revision INTEGER NOT NULL,
    last_committed_revision INTEGER,
    random_seed TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_results (
    request_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_consumers (
    consumer_id TEXT NOT NULL,
    world_id TEXT NOT NULL,
    acknowledged_sequence INTEGER NOT NULL,
    PRIMARY KEY (consumer_id, world_id)
);
"""
