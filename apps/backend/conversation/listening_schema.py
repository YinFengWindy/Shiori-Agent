"""群聊旁听（#538）在 ``sessions.db`` 里的表。

- ``listening_messages``：入库的旁听消息（``listening_store``）；
- ``listening_groups`` / ``listening_toggles`` / ``listening_defaults``：每群的
  开关与上限覆盖、开关记录、全局默认上限（``listening_switches``）；
- ``listening_cursors``：每群旁听记录的整理游标（``listening_cursors``，#541）。
"""

from __future__ import annotations

import sqlite3


def ensure_listening_schema(connection: sqlite3.Connection) -> None:
    """Creates the listening tables; the caller owns the surrounding transaction.

    A platform message is stored once per group: ``external_message_id`` is
    unique within a thread where it is known (NULL where the plugin gave none).
    """
    connection.execute("""
        CREATE TABLE IF NOT EXISTS listening_messages (
            id                  TEXT PRIMARY KEY,
            thread_id           TEXT NOT NULL,
            seq                 INTEGER NOT NULL,
            sender_id           TEXT NOT NULL,
            content             TEXT NOT NULL,
            source              TEXT NOT NULL,
            external_message_id TEXT,
            ts                  TEXT NOT NULL,
            day                 TEXT NOT NULL,
            UNIQUE (thread_id, seq)
        )
        """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS listening_groups (
            thread_id  TEXT PRIMARY KEY,
            enabled    INTEGER NOT NULL DEFAULT 0,
            daily_cap  INTEGER,
            updated_at TEXT NOT NULL
        )
        """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS listening_toggles (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT NOT NULL,
            enabled   INTEGER NOT NULL,
            operator  TEXT NOT NULL,
            at        TEXT NOT NULL
        )
        """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS listening_defaults (
            id        INTEGER PRIMARY KEY CHECK (id = 1),
            daily_cap INTEGER NOT NULL
        )
        """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS listening_cursors (
            thread_id        TEXT PRIMARY KEY,
            consolidated_seq INTEGER NOT NULL
        )
        """)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_listening_messages_day"
        " ON listening_messages(thread_id, day)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_listening_messages_external"
        " ON listening_messages(thread_id, external_message_id)"
        " WHERE external_message_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_listening_toggles_thread"
        " ON listening_toggles(thread_id, id)"
    )
