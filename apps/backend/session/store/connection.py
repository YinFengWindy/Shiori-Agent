"""Session SQLite schema、迁移与连接生命周期。"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from conversation.store import ensure_conversation_schema
from infra.persistence.sqlite_transaction import immediate_transaction

from .common import CONTEXT_CURSOR_COLUMNS

# Triggers that keep the external-content messages_fts index in sync with messages.
_FTS_TRIGGERS = ("messages_ai", "messages_ad", "messages_au")


class _SessionConnection:
    @contextmanager
    def transaction(self):
        """Commit a synchronous message/metadata batch or roll it back together."""
        with self._lock, immediate_transaction(self._conn):
            yield

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._workspace = Path(db_path).expanduser().resolve().parent
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Conversation projections reenter the shared connection within undo's transaction.
        self._lock = threading.RLock()
        self._closed = False
        self._has_fts = False
        self._init_schema()
        from session.media_assets import adopt_persisted_media

        adopt_persisted_media(self._conn, self._workspace)

    def __del__(self) -> None:
        if not self._closed:
            try:
                self.close()
            except Exception:
                pass

    def _init_schema(self) -> None:
        # All schema DDL and upgrades share one transaction: a single commit, and a
        # failure anywhere rolls back to the previous schema instead of half of it.
        with self._lock, immediate_transaction(self._conn):
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    key               TEXT PRIMARY KEY,
                    created_at        TEXT NOT NULL,
                    updated_at        TEXT NOT NULL,
                    last_consolidated INTEGER NOT NULL DEFAULT 0,
                    metadata          TEXT
                )
                """)
            self._ensure_session_columns()
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id          TEXT PRIMARY KEY,
                    session_key TEXT NOT NULL,
                    seq         INTEGER NOT NULL,
                    role        TEXT NOT NULL,
                    content     TEXT,
                    tool_chain  TEXT,
                    extra       TEXT,
                    ts          TEXT NOT NULL,
                    UNIQUE (session_key, seq)
                )
                """)
            ensure_conversation_schema(self._conn)
            self._ensure_next_seq_values()
            self._ensure_fts()

    def _ensure_session_columns(self) -> None:
        rows = self._conn.execute("PRAGMA table_info(sessions)").fetchall()
        existing = {str(row["name"]) for row in rows}
        if "last_user_at" not in existing:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN last_user_at TEXT")
        if "last_proactive_at" not in existing:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN last_proactive_at TEXT")
        if "next_seq" not in existing:
            self._conn.execute(
                "ALTER TABLE sessions ADD COLUMN next_seq INTEGER NOT NULL DEFAULT 0"
            )
        if "maintenance_progress" not in existing:
            self._conn.execute(
                "ALTER TABLE sessions ADD COLUMN maintenance_progress TEXT"
            )
        # 角色会话按上下文的整理游标（#523）；NULL 表示未迁移，取 last_consolidated。
        for column in CONTEXT_CURSOR_COLUMNS.values():
            if column not in existing:
                self._conn.execute(f"ALTER TABLE sessions ADD COLUMN {column} INTEGER")

    def _ensure_next_seq_values(self) -> None:
        rows = self._conn.execute("SELECT key, next_seq FROM sessions").fetchall()
        for row in rows:
            session_key = str(row["key"])
            current = int(row["next_seq"] or 0)
            seq_row = self._conn.execute(
                "SELECT COALESCE(MAX(seq) + 1, 0) AS next_seq FROM messages WHERE session_key = ?",
                (session_key,),
            ).fetchone()
            required = int((seq_row["next_seq"] if seq_row else 0) or 0)
            if current < required:
                self._conn.execute(
                    "UPDATE sessions SET next_seq = ? WHERE key = ?",
                    (required, session_key),
                )

    def _ensure_fts(self) -> None:
        # FTS is optional: a savepoint confines a failed FTS setup to its own
        # statements so the enclosing schema transaction can still commit.
        self._conn.execute("SAVEPOINT ensure_fts")
        try:
            self._migrate_fts()
        except sqlite3.OperationalError:
            # Errors such as SQLITE_FULL/IOERR roll back the whole transaction,
            # taking the savepoint with it; surface the real failure then.
            if not self._conn.in_transaction:
                raise
            self._conn.execute("ROLLBACK TO ensure_fts")
            self._conn.execute("RELEASE ensure_fts")
            self._has_fts = False
            return
        self._conn.execute("RELEASE ensure_fts")
        self._has_fts = True

    def _migrate_fts(self) -> None:
        """Bring messages_fts to the trigram shape, rebuilding only when it changed."""
        # The tokenizer is only recorded in the CREATE VIRTUAL TABLE statement;
        # fts5's *_config shadow table holds nothing but the format version.
        row = self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ).fetchone()
        fts_sql = str(row["sql"]) if row else None
        triggers = {
            str(trigger["name"])
            for trigger in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name IN "
                f"({', '.join('?' for _ in _FTS_TRIGGERS)})",
                _FTS_TRIGGERS,
            ).fetchall()
        }
        is_trigram = fts_sql is not None and "trigram" in fts_sql.lower()
        if is_trigram and len(triggers) == len(_FTS_TRIGGERS):
            # Up to date: only confirm the fts5 module can open the table, so a
            # build without FTS5 still falls back to LIKE search.
            self._conn.execute("SELECT 1 FROM messages_fts LIMIT 0").fetchall()
            return
        if fts_sql is not None and not is_trigram:
            # trigram supports CJK substring matching; the old unicode61 default
            # does not, so a legacy index is dropped and rebuilt from scratch.
            self._conn.execute("DROP TABLE messages_fts")
            for trigger in _FTS_TRIGGERS:
                self._conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")

        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                content='messages',
                content_rowid='rowid',
                tokenize='trigram'
            )
            """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
            END
            """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.rowid, old.content);
            END
            """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content)
                VALUES('delete', old.rowid, old.content);
                INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
            END
            """)
        # A new index, or one that missed writes while a trigger was absent,
        # must be repopulated from messages.
        self._conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()
