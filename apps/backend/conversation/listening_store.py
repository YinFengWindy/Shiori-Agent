"""群聊旁听记录（#538）：开启旁听的群里没有 @ 或回复角色的消息。

每个群（角色在该群的会话线程）一份，与角色会话分开存在 ``sessions.db`` 的
``listening_messages`` 里，按线程递增的 ``seq`` 排序，带与普通消息相同的来源
快照（``MessageSource.to_metadata()``）。

每群每天（本地日期）至多入库上限条（``listening_switches``）；超出的消息只留
在内存里每群最近 ``RECENT_WINDOW_SIZE`` 条的窗口中作前文，不入库、不整理、
不在小手机显示。同一条平台消息（``external_message_id``）只收一次。关闭旁听
不删除已有记录。
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
from typing import Any

from conversation.listening_switches import ListeningSwitches
from infra.persistence.sqlite_transaction import immediate_transaction

# 内存最近窗口每群保留的条数，也是 ``recent`` 默认返回的条数。
RECENT_WINDOW_SIZE = 30
# 小手机翻页的默认与最大页长。
_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class ListeningMessage:
    """一条旁听到的群消息。

    ``seq`` 是入库后在本群旁听记录里的顺序；只留在内存窗口的消息为 None。
    ``source`` 是来源快照（群名、发送者昵称、是否用户本人、被 @ 成员 ID 等），
    ``timestamp`` 是带本地时区的 ISO 时间；``external_message_id`` 为空表示
    插件没有给出平台消息 ID。
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


class GroupListeningStore:
    """Keeps what a role hears in its groups, under each group's switch and cap.

    Shares ``sessions.db``'s connection and lock with the conversation store.
    One instance lives on that store (``ConversationStore.listening``), so the
    in-memory recent window is the same for the channel hub that writes it and
    the prompt assembly that reads it. ``switches`` holds each group's
    listening switch and cap.
    """

    def __init__(
        self, connection: sqlite3.Connection, lock: threading.Lock | threading.RLock
    ) -> None:
        self._conn = connection
        self._lock = lock
        self.switches = ListeningSwitches(connection, lock)
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
        already heard (a replay, stored or in the window). Otherwise the
        message is stored while the group's count for its local day is under
        the daily cap, and kept only in the recent window past it (``seq``
        None). Listeners hear stored messages after the commit.
        """
        if not self.switches.settings(thread_id).enabled:
            return None
        cap = self.switches.daily_cap(thread_id)
        moment = timestamp.astimezone()
        day = moment.date().isoformat()
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
        with self._lock:
            if self._already_heard(thread_id, external_message_id):
                return None
            count = self._conn.execute(
                "SELECT COUNT(1) FROM listening_messages WHERE thread_id = ? AND day = ?",
                (thread_id, day),
            ).fetchone()[0]
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
                        external_message_id or None,
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

    def _already_heard(self, thread_id: str, external_message_id: str) -> bool:
        """The platform message is stored or in the window; caller holds the lock."""
        if not external_message_id:
            return False
        if any(
            message.external_message_id == external_message_id
            for message in self._window.get(thread_id, ())
        ):
            return True
        return (
            self._conn.execute(
                """
                SELECT 1 FROM listening_messages
                WHERE thread_id = ? AND external_message_id = ?
                LIMIT 1
                """,
                (thread_id, external_message_id),
            ).fetchone()
            is not None
        )


_COLUMNS = "id, thread_id, seq, sender_id, content, source, external_message_id, ts"


def _row_to_message(row: sqlite3.Row) -> ListeningMessage:
    return ListeningMessage(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        seq=int(row["seq"]),
        sender_id=str(row["sender_id"]),
        content=str(row["content"]),
        source=json.loads(row["source"]),
        external_message_id=str(row["external_message_id"] or ""),
        timestamp=str(row["ts"]),
    )
