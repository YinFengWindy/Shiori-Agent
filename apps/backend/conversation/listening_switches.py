"""群聊旁听的开关与上限（#538）：每群的开关（默认关）与每日入库上限覆盖、
每次开关的记录（操作方、时间、新状态），以及全局默认上限。"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from infra.persistence.sqlite_transaction import immediate_transaction

# 每群每日入库上限的全局默认值与下限。
DEFAULT_DAILY_CAP = 200
MIN_DAILY_CAP = 1

# 开关旁听的操作方：用户经小手机，或角色经工具（#540）。
ListeningOperator = Literal["user", "role"]


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


def valid_daily_cap(value: object) -> int:
    """``value`` as a daily cap: an integer of at least ``MIN_DAILY_CAP``, else ValueError."""
    if isinstance(value, bool) or not isinstance(value, int) or value < MIN_DAILY_CAP:
        raise ValueError(f"每日入库上限必须是不小于 {MIN_DAILY_CAP} 的整数")
    return value


def _operator(value: object) -> ListeningOperator:
    if value == "user":
        return "user"
    if value == "role":
        return "role"
    raise ValueError(f"未知的旁听操作方: {value!r}")


def _now() -> str:
    return datetime.now().astimezone().isoformat()


class ListeningSwitches:
    """Each group's listening switch and cap, the switch log and the default cap.

    Shares ``sessions.db``'s connection and lock with the conversation store.
    """

    def __init__(
        self, connection: sqlite3.Connection, lock: threading.Lock | threading.RLock
    ) -> None:
        self._conn = connection
        self._lock = lock

    def settings(self, thread_id: str) -> ListeningSettings:
        """The group's listening switch and cap override; off without a row."""
        with self._lock:
            return self._settings(thread_id)

    def daily_cap(self, thread_id: str) -> int:
        """The cap in force for the group: its override, else the default."""
        with self._lock:
            return self._settings(thread_id).daily_cap or self._default_daily_cap()

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

    def set_daily_cap(self, thread_id: str, cap: object) -> ListeningSettings:
        """Overrides the group's daily cap; None goes back to the global default."""
        clean = None if cap is None else valid_daily_cap(cap)
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

    def set_default_daily_cap(self, cap: object) -> int:
        """Sets the global default daily cap."""
        clean = valid_daily_cap(cap)
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
