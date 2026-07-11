from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from conversation.models import ContactRecord, StateRecord, ThreadRecord


def ensure_conversation_schema(connection: sqlite3.Connection) -> None:
    """Ensures `sessions.db` exposes the new conversation tables and message columns."""
    _ensure_base_legacy_tables(connection)
    _ensure_conversation_tables(connection)
    _ensure_message_columns(connection)
    _ensure_indexes(connection)


def _ensure_base_legacy_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            key               TEXT PRIMARY KEY,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            last_consolidated INTEGER NOT NULL DEFAULT 0,
            metadata          TEXT
        )
        """
    )
    connection.execute(
        """
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
        """
    )


def _ensure_conversation_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id          TEXT PRIMARY KEY,
            role_id     TEXT NOT NULL,
            kind        TEXT NOT NULL,
            channel     TEXT NOT NULL,
            external_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            metadata    TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            id                 TEXT PRIMARY KEY,
            role_id            TEXT NOT NULL,
            contact_id         TEXT NOT NULL,
            channel            TEXT NOT NULL,
            thread_kind        TEXT NOT NULL,
            external_thread_id TEXT NOT NULL,
            legacy_session_key TEXT UNIQUE,
            archived           INTEGER NOT NULL DEFAULT 0,
            metadata           TEXT NOT NULL DEFAULT '{}',
            created_at         TEXT NOT NULL,
            updated_at         TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_state (
            thread_id   TEXT PRIMARY KEY,
            summary     TEXT NOT NULL DEFAULT '',
            metadata    TEXT NOT NULL DEFAULT '{}',
            updated_at  TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_state (
            contact_id  TEXT PRIMARY KEY,
            summary     TEXT NOT NULL DEFAULT '',
            metadata    TEXT NOT NULL DEFAULT '{}',
            updated_at  TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS role_state (
            role_id     TEXT PRIMARY KEY,
            summary     TEXT NOT NULL DEFAULT '',
            metadata    TEXT NOT NULL DEFAULT '{}',
            updated_at  TEXT NOT NULL
        )
        """
    )


def _ensure_message_columns(connection: sqlite3.Connection) -> None:
    rows = connection.execute("PRAGMA table_info(messages)").fetchall()
    existing = {str(row["name"]) for row in rows}
    additions = {
        "thread_id": "ALTER TABLE messages ADD COLUMN thread_id TEXT",
        "sender_role": "ALTER TABLE messages ADD COLUMN sender_role TEXT",
        "media": "ALTER TABLE messages ADD COLUMN media TEXT",
        "external_message_id": "ALTER TABLE messages ADD COLUMN external_message_id TEXT",
        "delivery_status": "ALTER TABLE messages ADD COLUMN delivery_status TEXT",
    }
    for name, sql in additions.items():
        if name not in existing:
            connection.execute(sql)


def _ensure_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_contacts_role_id ON contacts(role_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_threads_role_id ON threads(role_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_threads_contact_id ON threads(contact_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_external_message_id ON messages(external_message_id)"
    )


class ConversationStore:
    """Owns the thread/contact conversation schema layered onto `sessions.db`."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        connection: sqlite3.Connection | None = None,
        lock: threading.Lock | None = None,
    ) -> None:
        self.db_path = str(db_path)
        self._conn = connection or sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = lock or threading.Lock()
        self._owns_connection = connection is None
        self._closed = False
        self.ensure_schema()

    def close(self) -> None:
        if not self._owns_connection or self._closed:
            return
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()

    def ensure_schema(self) -> None:
        with self._lock:
            ensure_conversation_schema(self._conn)
            self._conn.commit()

    def list_legacy_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT key, created_at, updated_at, metadata
                FROM sessions
                ORDER BY updated_at ASC, key ASC
                """
            ).fetchall()
        return [
            {
                "key": str(row["key"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "metadata": json.loads(row["metadata"] or "{}"),
            }
            for row in rows
        ]

    def list_contacts(self) -> list[ContactRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, role_id, kind, channel, external_id, display_name, metadata, created_at, updated_at
                FROM contacts
                ORDER BY role_id ASC, channel ASC, external_id ASC, id ASC
                """
            ).fetchall()
        return [self._row_to_contact(row) for row in rows]

    def list_threads(self) -> list[ThreadRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, role_id, contact_id, channel, thread_kind, external_thread_id,
                       legacy_session_key, archived, metadata, created_at, updated_at
                FROM threads
                ORDER BY role_id ASC, channel ASC, created_at ASC, id ASC
                """
            ).fetchall()
        return [self._row_to_thread(row) for row in rows]

    def get_thread_by_legacy_session_key(self, session_key: str) -> ThreadRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, role_id, contact_id, channel, thread_kind, external_thread_id,
                       legacy_session_key, archived, metadata, created_at, updated_at
                FROM threads
                WHERE legacy_session_key = ?
                """,
                (session_key,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_thread(row)

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        """Returns one formal thread by its business identifier."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, role_id, contact_id, channel, thread_kind, external_thread_id,
                       legacy_session_key, archived, metadata, created_at, updated_at
                FROM threads
                WHERE id = ?
                """,
                (thread_id,),
            ).fetchone()
        return self._row_to_thread(row) if row is not None else None

    def get_contact(self, contact_id: str) -> ContactRecord | None:
        """Returns one formal contact by its business identifier."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, role_id, kind, channel, external_id, display_name, metadata, created_at, updated_at
                FROM contacts
                WHERE id = ?
                """,
                (contact_id,),
            ).fetchone()
        return self._row_to_contact(row) if row is not None else None

    def upsert_contact(
        self,
        *,
        contact_id: str,
        role_id: str,
        kind: str,
        channel: str,
        external_id: str,
        display_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> ContactRecord:
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO contacts (
                    id, role_id, kind, channel, external_id, display_name, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role_id = excluded.role_id,
                    kind = excluded.kind,
                    channel = excluded.channel,
                    external_id = excluded.external_id,
                    display_name = excluded.display_name,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    contact_id,
                    role_id,
                    kind,
                    channel,
                    external_id,
                    display_name,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = self._conn.execute(
                """
                SELECT id, role_id, kind, channel, external_id, display_name, metadata, created_at, updated_at
                FROM contacts
                WHERE id = ?
                """,
                (contact_id,),
            ).fetchone()
            self._conn.commit()
        if row is None:
            raise ValueError(f"contact upsert failed: {contact_id}")
        return self._row_to_contact(row)

    def upsert_thread(
        self,
        *,
        thread_id: str,
        role_id: str,
        contact_id: str,
        channel: str,
        thread_kind: str,
        external_thread_id: str,
        legacy_session_key: str,
        metadata: dict[str, Any] | None = None,
        archived: bool = False,
    ) -> ThreadRecord:
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO threads (
                    id, role_id, contact_id, channel, thread_kind, external_thread_id,
                    legacy_session_key, archived, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role_id = excluded.role_id,
                    contact_id = excluded.contact_id,
                    channel = excluded.channel,
                    thread_kind = excluded.thread_kind,
                    external_thread_id = excluded.external_thread_id,
                    legacy_session_key = excluded.legacy_session_key,
                    archived = excluded.archived,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    thread_id,
                    role_id,
                    contact_id,
                    channel,
                    thread_kind,
                    external_thread_id,
                    legacy_session_key,
                    1 if archived else 0,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            row = self._conn.execute(
                """
                SELECT id, role_id, contact_id, channel, thread_kind, external_thread_id,
                       legacy_session_key, archived, metadata, created_at, updated_at
                FROM threads
                WHERE id = ?
                """,
                (thread_id,),
            ).fetchone()
            self._conn.commit()
        if row is None:
            raise ValueError(f"thread upsert failed: {thread_id}")
        return self._row_to_thread(row)

    def replace_unresolved_thread(
        self,
        unresolved_thread_id: str,
        *,
        thread_id: str,
        role_id: str,
        contact_id: str,
        channel: str,
        thread_kind: str,
        external_thread_id: str,
        legacy_session_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> ThreadRecord:
        """Promotes an unresolved legacy thread after its role binding becomes known."""
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM threads WHERE id = ? AND thread_kind = 'legacy/unresolved'",
                (unresolved_thread_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"unresolved thread 不存在: {unresolved_thread_id}")
            self._conn.execute(
                """
                UPDATE threads
                SET id = ?, role_id = ?, contact_id = ?, channel = ?, thread_kind = ?,
                    external_thread_id = ?, legacy_session_key = ?, metadata = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    thread_id,
                    role_id,
                    contact_id,
                    channel,
                    thread_kind,
                    external_thread_id,
                    legacy_session_key,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                    unresolved_thread_id,
                ),
            )
            self._conn.execute(
                "UPDATE messages SET thread_id = ? WHERE thread_id = ?",
                (thread_id, unresolved_thread_id),
            )
            self._conn.execute(
                "UPDATE thread_state SET thread_id = ? WHERE thread_id = ?",
                (thread_id, unresolved_thread_id),
            )
            row = self._conn.execute(
                """
                SELECT id, role_id, contact_id, channel, thread_kind, external_thread_id,
                       legacy_session_key, archived, metadata, created_at, updated_at
                FROM threads
                WHERE id = ?
                """,
                (thread_id,),
            ).fetchone()
            self._conn.commit()
        if row is None:
            raise ValueError(f"unresolved thread 升级失败: {unresolved_thread_id}")
        return self._row_to_thread(row)

    def upsert_thread_state(
        self,
        thread_id: str,
        *,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> StateRecord:
        return self._upsert_state(
            "thread_state",
            "thread_id",
            thread_id,
            summary=summary,
            metadata=metadata,
        )

    def get_thread_state(self, thread_id: str) -> StateRecord | None:
        """Returns the current derived state for a formal thread."""
        return self._get_state("thread_state", "thread_id", thread_id)

    def upsert_contact_state(
        self,
        contact_id: str,
        *,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> StateRecord:
        return self._upsert_state(
            "contact_state",
            "contact_id",
            contact_id,
            summary=summary,
            metadata=metadata,
        )

    def get_contact_state(self, contact_id: str) -> StateRecord | None:
        """Returns the current derived state for a formal contact."""
        return self._get_state("contact_state", "contact_id", contact_id)

    def upsert_role_state(
        self,
        role_id: str,
        *,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> StateRecord:
        return self._upsert_state(
            "role_state",
            "role_id",
            role_id,
            summary=summary,
            metadata=metadata,
        )

    def get_role_state(self, role_id: str) -> StateRecord | None:
        """Returns the current derived state for a formal role."""
        return self._get_state("role_state", "role_id", role_id)

    def count_unassigned_messages(self, session_key: str) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(1) AS c
                FROM messages
                WHERE session_key = ? AND COALESCE(thread_id, '') = ''
                """,
                (session_key,),
            ).fetchone()
        return int((row["c"] if row else 0) or 0)

    def assign_legacy_messages_to_thread(self, session_key: str, thread_id: str) -> int:
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE messages
                SET thread_id = ?,
                    sender_role = COALESCE(NULLIF(sender_role, ''), role)
                WHERE session_key = ? AND COALESCE(thread_id, '') = ''
                """,
                (thread_id, session_key),
            )
            self._conn.execute(
                "UPDATE threads SET updated_at = ? WHERE id = ?",
                (now, thread_id),
            )
            self._conn.commit()
        return int(cur.rowcount or 0)

    def list_message_thread_ids(self, session_key: str) -> list[str | None]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT thread_id
                FROM messages
                WHERE session_key = ?
                ORDER BY seq ASC
                """,
                (session_key,),
            ).fetchall()
        return [cast_value if cast_value else None for cast_value in (row["thread_id"] for row in rows)]

    def list_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Returns persisted message facts belonging to one formal thread."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, sender_role, content, media, external_message_id, delivery_status, ts
                FROM messages
                WHERE thread_id = ?
                ORDER BY ts ASC, id ASC
                """,
                (thread_id,),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "sender_role": str(row["sender_role"] or ""),
                "content": str(row["content"] or ""),
                "media": json.loads(row["media"] or "[]"),
                "external_message_id": str(row["external_message_id"] or ""),
                "delivery_status": str(row["delivery_status"] or ""),
                "ts": str(row["ts"]),
            }
            for row in rows
        ]

    def has_external_message(self, thread_id: str, external_message_id: str) -> bool:
        """Checks whether a channel delivery has already been archived for a thread."""
        clean_external_id = str(external_message_id or "").strip()
        if not clean_external_id:
            return False
        with self._lock:
            row = self._conn.execute(
                """
                SELECT 1
                FROM messages
                WHERE thread_id = ? AND external_message_id = ?
                LIMIT 1
                """,
                (thread_id, clean_external_id),
            ).fetchone()
        return row is not None

    def _upsert_state(
        self,
        table: str,
        owner_column: str,
        owner_id: str,
        *,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> StateRecord:
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            self._conn.execute(
                f"""
                INSERT INTO {table} ({owner_column}, summary, metadata, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT({owner_column}) DO UPDATE SET
                    summary = excluded.summary,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    owner_id,
                    summary,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    now,
                ),
            )
            row = self._conn.execute(
                f"SELECT {owner_column}, summary, metadata, updated_at FROM {table} WHERE {owner_column} = ?",
                (owner_id,),
            ).fetchone()
            self._conn.commit()
        if row is None:
            raise ValueError(f"state upsert failed: {table}:{owner_id}")
        return StateRecord(
            owner_id=str(row[owner_column]),
            summary=str(row["summary"] or ""),
            metadata=json.loads(row["metadata"] or "{}"),
            updated_at=str(row["updated_at"]),
        )

    def _get_state(
        self,
        table: str,
        owner_column: str,
        owner_id: str,
    ) -> StateRecord | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {owner_column}, summary, metadata, updated_at FROM {table} WHERE {owner_column} = ?",
                (owner_id,),
            ).fetchone()
        if row is None:
            return None
        return StateRecord(
            owner_id=str(row[owner_column]),
            summary=str(row["summary"] or ""),
            metadata=json.loads(row["metadata"] or "{}"),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_contact(row: sqlite3.Row) -> ContactRecord:
        return ContactRecord(
            id=str(row["id"]),
            role_id=str(row["role_id"]),
            kind=str(row["kind"]),
            channel=str(row["channel"]),
            external_id=str(row["external_id"]),
            display_name=str(row["display_name"]),
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_thread(row: sqlite3.Row) -> ThreadRecord:
        return ThreadRecord(
            id=str(row["id"]),
            role_id=str(row["role_id"]),
            contact_id=str(row["contact_id"]),
            channel=str(row["channel"]),
            thread_kind=str(row["thread_kind"]),
            external_thread_id=str(row["external_thread_id"]),
            legacy_session_key=str(row["legacy_session_key"] or ""),
            archived=bool(row["archived"]),
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
