from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

import session.store.connection as connection_module
from session.store import SessionStore

# Fresh-database shape produced before schema setup shared one transaction: the
# CREATE statements plus the column migrations appended in this order.
EXPECTED_SESSIONS_COLUMNS = [
    (0, "key", "TEXT", 0, None, 1),
    (1, "created_at", "TEXT", 1, None, 0),
    (2, "updated_at", "TEXT", 1, None, 0),
    (3, "last_consolidated", "INTEGER", 1, "0", 0),
    (4, "metadata", "TEXT", 0, None, 0),
    (5, "last_user_at", "TEXT", 0, None, 0),
    (6, "last_proactive_at", "TEXT", 0, None, 0),
    (7, "next_seq", "INTEGER", 1, "0", 0),
]
EXPECTED_MESSAGES_COLUMNS = [
    (0, "id", "TEXT", 0, None, 1),
    (1, "session_key", "TEXT", 1, None, 0),
    (2, "seq", "INTEGER", 1, None, 0),
    (3, "role", "TEXT", 1, None, 0),
    (4, "content", "TEXT", 0, None, 0),
    (5, "tool_chain", "TEXT", 0, None, 0),
    (6, "extra", "TEXT", 0, None, 0),
    (7, "ts", "TEXT", 1, None, 0),
    (8, "thread_id", "TEXT", 0, None, 0),
    (9, "sender_role", "TEXT", 0, None, 0),
    (10, "media", "TEXT", 0, None, 0),
    (11, "external_message_id", "TEXT", 0, None, 0),
    (12, "delivery_status", "TEXT", 0, None, 0),
]
EXPECTED_OBJECTS = {
    ("index", "idx_contacts_role_id"),
    ("index", "idx_messages_external_message_id"),
    ("index", "idx_messages_thread_id"),
    ("index", "idx_threads_contact_id"),
    ("index", "idx_threads_role_id"),
    ("index", "sqlite_autoindex_contact_state_1"),
    ("index", "sqlite_autoindex_contacts_1"),
    ("index", "sqlite_autoindex_messages_1"),
    ("index", "sqlite_autoindex_messages_2"),
    ("index", "sqlite_autoindex_role_state_1"),
    ("index", "sqlite_autoindex_sessions_1"),
    ("index", "sqlite_autoindex_thread_state_1"),
    ("index", "sqlite_autoindex_threads_1"),
    ("index", "sqlite_autoindex_threads_2"),
    ("table", "contact_state"),
    ("table", "contacts"),
    ("table", "media_migrations"),
    ("table", "messages"),
    ("table", "messages_fts"),
    ("table", "messages_fts_config"),
    ("table", "messages_fts_data"),
    ("table", "messages_fts_docsize"),
    ("table", "messages_fts_idx"),
    ("table", "role_state"),
    ("table", "sessions"),
    ("table", "thread_state"),
    ("table", "threads"),
    ("trigger", "messages_ad"),
    ("trigger", "messages_ai"),
    ("trigger", "messages_au"),
}


def _schema_objects(db_path: Path) -> set[tuple[str, str]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return set(conn.execute("SELECT type, name FROM sqlite_master").fetchall())


def _columns(db_path: Path, table: str) -> list[tuple]:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(f"PRAGMA table_info({table})").fetchall()


def _create_legacy_database(db_path: Path) -> None:
    """Builds the pre-migration shape: base tables, unicode61 FTS, no new columns."""
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript("""
            CREATE TABLE sessions (
                key TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_consolidated INTEGER NOT NULL DEFAULT 0,
                metadata TEXT
            );
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                session_key TEXT NOT NULL,
                seq INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_chain TEXT,
                extra TEXT,
                ts TEXT NOT NULL,
                UNIQUE (session_key, seq)
            );
            CREATE VIRTUAL TABLE messages_fts USING fts5(
                content, content='messages', content_rowid='rowid'
            );
            INSERT INTO sessions VALUES ('role:mira', 't0', 't1', 2, '{}');
            INSERT INTO messages VALUES
                ('role:mira:0', 'role:mira', 0, 'user', '你好世界', NULL, NULL, 't0'),
                ('role:mira:1', 'role:mira', 1, 'assistant', 'hello', NULL, NULL, 't1'),
                ('role:mira:4', 'role:mira', 4, 'user', 'later', NULL, NULL, 't2');
            """)


def test_fresh_schema_matches_previous_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    SessionStore(db_path).close()

    assert _schema_objects(db_path) == EXPECTED_OBJECTS
    assert _columns(db_path, "sessions") == EXPECTED_SESSIONS_COLUMNS
    assert _columns(db_path, "messages") == EXPECTED_MESSAGES_COLUMNS


def test_schema_setup_runs_in_one_transaction_with_single_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    traced: list[tuple[str, bool]] = []
    real_connect = sqlite3.connect

    def traced_connect(*args, **kwargs) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)

        def trace(sql: str) -> None:
            # "--" marks statements FTS5 runs internally on behalf of a traced one.
            if not sql.startswith("--"):
                traced.append((sql.split()[0].upper(), conn.in_transaction))

        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(connection_module.sqlite3, "connect", traced_connect)
    # Media adoption owns a separate, later transaction; isolate schema setup.
    monkeypatch.setattr(
        "session.media_assets.adopt_persisted_media", lambda *_args: None
    )

    SessionStore(tmp_path / "sessions.db").close()

    assert traced[0] == ("BEGIN", False)
    assert [verb for verb, _ in traced].count("COMMIT") == 1
    assert traced[-1] == ("COMMIT", True)
    # Every DDL/DML statement between BEGIN and COMMIT runs inside the transaction.
    assert all(in_transaction for _, in_transaction in traced[1:])
    assert sum(verb == "ALTER" for verb, _ in traced) == 8


def test_failed_schema_setup_leaves_fresh_database_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "sessions.db"
    real_ensure = connection_module.ensure_conversation_schema

    def failing_ensure(conn: sqlite3.Connection) -> None:
        real_ensure(conn)
        raise RuntimeError("injected schema failure")

    monkeypatch.setattr(connection_module, "ensure_conversation_schema", failing_ensure)

    with pytest.raises(RuntimeError, match="injected schema failure"):
        SessionStore(db_path)

    assert _schema_objects(db_path) == set()


def test_failed_upgrade_keeps_legacy_schema_and_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "sessions.db"
    _create_legacy_database(db_path)
    legacy_objects = _schema_objects(db_path)
    legacy_sessions = _columns(db_path, "sessions")
    legacy_messages = _columns(db_path, "messages")
    real_ensure = connection_module.ensure_conversation_schema

    def failing_ensure(conn: sqlite3.Connection) -> None:
        real_ensure(conn)
        raise RuntimeError("injected schema failure")

    monkeypatch.setattr(connection_module, "ensure_conversation_schema", failing_ensure)

    with pytest.raises(RuntimeError, match="injected schema failure"):
        SessionStore(db_path)

    assert _schema_objects(db_path) == legacy_objects
    assert _columns(db_path, "sessions") == legacy_sessions
    assert _columns(db_path, "messages") == legacy_messages
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone() == (3,)


def test_legacy_database_upgrades_columns_cursor_and_fts(tmp_path: Path) -> None:
    db_path = tmp_path / "sessions.db"
    _create_legacy_database(db_path)

    store = SessionStore(db_path)
    try:
        assert store._has_fts is True
        assert store.next_seq("role:mira") == 5
        assert [
            row["content"] for row in store.fetch_session_messages("role:mira")
        ] == [
            "你好世界",
            "hello",
            "later",
        ]
    finally:
        store.close()

    assert _schema_objects(db_path) == EXPECTED_OBJECTS
    assert _columns(db_path, "sessions") == EXPECTED_SESSIONS_COLUMNS
    assert _columns(db_path, "messages") == EXPECTED_MESSAGES_COLUMNS
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute(
            "SELECT last_consolidated, next_seq FROM sessions WHERE key = 'role:mira'"
        ).fetchone() == (2, 5)
        fts_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'messages_fts'"
        ).fetchone()[0]
        assert "tokenize='trigram'" in fts_sql
        # The rebuilt trigram index covers pre-existing CJK rows.
        assert conn.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH '好世界'"
        ).fetchall() == [(1,)]
