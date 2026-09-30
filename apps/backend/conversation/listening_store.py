"""群聊旁听记录（#538）：开启旁听的群里没有 @ 或回复角色的消息。

每个群（角色在该群的会话线程）一份，与角色会话分开存在 ``sessions.db`` 里：

- ``listening_messages``：入库的旁听消息，按线程递增的 ``seq`` 排序，带与普通
  消息相同的来源快照（``MessageSource.to_metadata()``）；
- ``listening_groups``：每个群的旁听开关（默认关）与每日入库上限覆盖；
- ``listening_toggles``：每次开关的操作方、时间与新状态；
- ``listening_defaults``：全局默认的每日入库上限（只有一行）。

每群每天（本地日期）至多入库上限条；超出的消息只留在内存里每群最近
``RECENT_WINDOW_SIZE`` 条的窗口中作前文，不入库、不整理、不在小手机显示。
关闭旁听不删除已有记录。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

from infra.persistence.sqlite_transaction import immediate_transaction

# 每群每日入库上限的全局默认值与下限。
DEFAULT_DAILY_CAP = 200
MIN_DAILY_CAP = 1
# 内存最近窗口每群保留的条数，也是 ``recent`` 默认返回的条数。
RECENT_WINDOW_SIZE = 30
# 小手机翻页的默认与最大页长。
_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100

# 开关旁听的操作方：用户经小手机，或角色经工具（#540）。
ListeningOperator = Literal["user", "role"]


@dataclass(frozen=True)
class ListeningMessage:
    """一条旁听到的群消息。

    ``seq`` 是入库后在本群旁听记录里的顺序；只留在内存窗口的消息为 None。
    ``source`` 是来源快照（群名、发送者昵称、是否用户本人、被 @ 成员 ID 等），
    ``timestamp`` 是带本地时区的 ISO 时间。
    """

    id: str
    thread_id: str
    seq: int | None
    sender_id: str
    content: str
    source: dict[str, Any]
    external_message_id: str
    timestamp: str

    @property
    def stored(self) -> bool:
        """这条消息已入库（没有超出当日上限）。"""
        return self.seq is not None


@dataclass(frozen=True)
class ListeningSettings:
    """一个群的旁听设置：开关与每日上限覆盖（None 表示用全局默认）。"""

    thread_id: str
    enabled: bool
    daily_cap: int | None


@dataclass(frozen=True)
class ListeningToggle:
    """一次旁听开关：谁、什么时候、开还是关。"""

    thread_id: str
    enabled: bool
    operator: ListeningOperator
    at: str


def ensure_listening_schema(connection: sqlite3.Connection) -> None:
    """Creates the listening tables; the caller owns the surrounding transaction."""
    connection.execute("""
        CREATE TABLE IF NOT EXISTS listening_messages (
            id                  TEXT PRIMARY KEY,
            thread_id           TEXT NOT NULL,
            seq                 INTEGER NOT NULL,
            sender_id           TEXT NOT NULL,
            content             TEXT NOT NULL,
            source              TEXT NOT NULL,
            external_message_id TEXT NOT NULL DEFAULT '',
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
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_listening_messages_day"
        " ON listening_messages(thread_id, day)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_listening_messages_external"
        " ON listening_messages(thread_id, external_message_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_listening_toggles_thread"
        " ON listening_toggles(thread_id, id)"
    )


def _operator(value: object) -> ListeningOperator:
    if value == "user":
        return "user"
    if value == "role":
        return "role"
    raise ValueError(f"未知的旁听操作方: {value!r}")


def _valid_cap(cap: int) -> int:
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < MIN_DAILY_CAP:
        raise ValueError(f"每日入库上限必须是不小于 {MIN_DAILY_CAP} 的整数")
    return cap


def _now() -> str:
    return datetime.now().astimezone().isoformat()


class GroupListeningStore:
    """Stores what a role hears in its groups, and each group's listening switch.

    Shares ``sessions.db``'s connection and lock with the conversation store.
    One instance lives on that store (``ConversationStore.listening``), so the
    in-memory recent window is the same for the channel hub that writes it and
    the prompt assembly that reads it.
    """

    def __init__(
        self, connection: sqlite3.Connection, lock: threading.Lock | threading.RLock
    ) -> None:
        self._conn = connection
        self._lock = lock
        self._window: dict[str, deque[ListeningMessage]] = {}
        self._listeners: list[Callable[[ListeningMessage], None]] = []

    def add_heard_listener(self, listener: Callable[[ListeningMessage], None]) -> None:
        """Subscribes to messages newly stored (not window-only ones)."""
        self._listeners.append(listener)

    def remove_heard_listener(
        self, listener: Callable[[ListeningMessage], None]
    ) -> None:
        """Withdraws a listener added with ``add_heard_listener``."""
        self._listeners = [known for known in self._listeners if known != listener]

    def hear(
        self,
        thread_id: str,
        *,
        sender_id: str,
        content: str,
        source: dict[str, Any],
        external_message_id: str,
        timestamp: datetime,
    ) -> ListeningMessage | None:
        """Takes one unaddressed group message of ``thread_id``.

        None when listening is off for the group, or the platform message was
        already stored (a replay). Otherwise the message is stored while the
        group's count for its local day is under the daily cap, and kept only
        in the recent window past it (``seq`` None). Listeners hear stored
        messages after the commit.
        """
        moment = timestamp.astimezone()
        day = moment.date().isoformat()
        with self._lock:
            settings = self._settings(thread_id)
            if not settings.enabled:
                return None
            if (
                external_message_id
                and self._conn.execute(
                    """
                SELECT 1 FROM listening_messages
                WHERE thread_id = ? AND external_message_id = ?
                LIMIT 1
                """,
                    (thread_id, external_message_id),
                ).fetchone()
            ):
                return None
            cap = settings.daily_cap or self._default_daily_cap()
            count = self._conn.execute(
                "SELECT COUNT(1) FROM listening_messages WHERE thread_id = ? AND day = ?",
                (thread_id, day),
            ).fetchone()[0]
            heard = ListeningMessage(
                id=f"listen:{uuid.uuid4().hex}",
                thread_id=thread_id,
                seq=None,
                sender_id=sender_id,
                content=content,
                source=dict(source),
                external_message_id=external_message_id,
                timestamp=moment.isoformat(),
            )
            if int(count) >= cap:
                self._window.setdefault(
                    thread_id, deque(maxlen=RECENT_WINDOW_SIZE)
                ).append(heard)
                return heard
            with immediate_transaction(self._conn):
                seq = self._conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM listening_messages WHERE thread_id = ?",
                    (thread_id,),
                ).fetchone()[0]
                stored = replace(heard, seq=int(seq))
                self._conn.execute(
                    """
                    INSERT INTO listening_messages (
                        id, thread_id, seq, sender_id, content, source,
                        external_message_id, ts, day
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored.id,
                        thread_id,
                        stored.seq,
                        sender_id,
                        content,
                        json.dumps(stored.source, ensure_ascii=False),
                        external_message_id,
                        stored.timestamp,
                        day,
                    ),
                )
        for listener in list(self._listeners):
            listener(stored)
        return stored

    def recent(
        self, thread_id: str, limit: int = RECENT_WINDOW_SIZE
    ) -> list[ListeningMessage]:
        """The group's newest ``limit`` heard messages, oldest first.

        Stored records and the window-only messages past the daily cap, merged
        by time: the listening part of a group turn's recent context (#539).
        The window lives in memory, so after a restart only stored ones remain.
        """
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT {_COLUMNS} FROM listening_messages
                WHERE thread_id = ?
                ORDER BY seq DESC
                LIMIT ?
                """,
                (thread_id, limit),
            ).fetchall()
            unstored = list(self._window.get(thread_id, ()))
        merged = [*(_row_to_message(row) for row in rows), *unstored]
        merged.sort(key=lambda message: datetime.fromisoformat(message.timestamp))
        return merged[-limit:] if limit > 0 else []

    def page(
        self, thread_id: str, *, before_seq: int | None = None, limit: int = _PAGE_SIZE
    ) -> dict[str, Any]:
        """One page of the group's stored records, oldest first.

        ``has_more`` tells whether older records remain before the page, and
        ``next_before_seq`` is the cursor for them (None for an empty page).
        """
        safe_limit = max(1, min(int(limit), _MAX_PAGE_SIZE))
        where = "thread_id = ?"
        params: list[object] = [thread_id]
        if before_seq is not None:
            where += " AND seq < ?"
            params.append(int(before_seq))
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT {_COLUMNS} FROM listening_messages
                WHERE {where}
                ORDER BY seq DESC
                LIMIT ?
                """,
                (*params, safe_limit + 1),
            ).fetchall()
        messages = [_row_to_message(row) for row in reversed(rows[:safe_limit])]
        return {
            "messages": messages,
            "has_more": len(rows) > safe_limit,
            "next_before_seq": messages[0].seq if messages else None,
        }

    def settings(self, thread_id: str) -> ListeningSettings:
        """The group's listening switch and cap override; off without a row."""
        with self._lock:
            return self._settings(thread_id)

    def set_enabled(
        self, thread_id: str, enabled: bool, *, operator: ListeningOperator
    ) -> ListeningSettings:
        """Turns listening on or off for a group, logging who changed it.

        Setting the state the group already has changes and logs nothing.
        Turning it off keeps the stored records.
        """
        operator = _operator(operator)
        now = _now()
        with self._lock:
            if self._settings(thread_id).enabled == enabled:
                return self._settings(thread_id)
            with immediate_transaction(self._conn):
                self._conn.execute(
                    """
                    INSERT INTO listening_groups (thread_id, enabled, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(thread_id) DO UPDATE SET
                        enabled = excluded.enabled, updated_at = excluded.updated_at
                    """,
                    (thread_id, int(enabled), now),
                )
                self._conn.execute(
                    """
                    INSERT INTO listening_toggles (thread_id, enabled, operator, at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (thread_id, int(enabled), operator, now),
                )
            return self._settings(thread_id)

    def set_daily_cap(self, thread_id: str, cap: int | None) -> ListeningSettings:
        """Overrides the group's daily cap; None goes back to the global default."""
        clean = None if cap is None else _valid_cap(cap)
        with self._lock, immediate_transaction(self._conn):
            self._conn.execute(
                """
                INSERT INTO listening_groups (thread_id, daily_cap, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    daily_cap = excluded.daily_cap, updated_at = excluded.updated_at
                """,
                (thread_id, clean, _now()),
            )
        return self.settings(thread_id)

    def toggles(self, thread_id: str, limit: int = 20) -> list[ListeningToggle]:
        """The group's newest ``limit`` switch changes, newest first."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT thread_id, enabled, operator, at FROM listening_toggles
                WHERE thread_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (thread_id, limit),
            ).fetchall()
        return [
            ListeningToggle(
                thread_id=str(row["thread_id"]),
                enabled=bool(row["enabled"]),
                operator=_operator(row["operator"]),
                at=str(row["at"]),
            )
            for row in rows
        ]

    def default_daily_cap(self) -> int:
        """The daily cap of every group without its own override."""
        with self._lock:
            return self._default_daily_cap()

    def set_default_daily_cap(self, cap: int) -> int:
        """Sets the global default daily cap."""
        clean = _valid_cap(cap)
        with self._lock, immediate_transaction(self._conn):
            self._conn.execute(
                """
                INSERT INTO listening_defaults (id, daily_cap) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET daily_cap = excluded.daily_cap
                """,
                (clean,),
            )
        return clean

    def _settings(self, thread_id: str) -> ListeningSettings:
        row = self._conn.execute(
            "SELECT enabled, daily_cap FROM listening_groups WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if row is None:
            return ListeningSettings(thread_id=thread_id, enabled=False, daily_cap=None)
        cap = row["daily_cap"]
        return ListeningSettings(
            thread_id=thread_id,
            enabled=bool(row["enabled"]),
            daily_cap=int(cap) if cap is not None else None,
        )

    def _default_daily_cap(self) -> int:
        row = self._conn.execute(
            "SELECT daily_cap FROM listening_defaults WHERE id = 1"
        ).fetchone()
        return int(row["daily_cap"]) if row is not None else DEFAULT_DAILY_CAP


_COLUMNS = "id, thread_id, seq, sender_id, content, source, external_message_id, ts"


def _row_to_message(row: sqlite3.Row) -> ListeningMessage:
    return ListeningMessage(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        seq=int(row["seq"]),
        sender_id=str(row["sender_id"]),
        content=str(row["content"]),
        source=json.loads(row["source"]),
        external_message_id=str(row["external_message_id"]),
        timestamp=str(row["ts"]),
    )
