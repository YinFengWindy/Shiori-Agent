"""Session 消息写入与管理操作。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .common import _MESSAGE_SELECT_COLUMNS

class _MessageMixin:
    def count_messages(self, session_key: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(1) AS c FROM messages WHERE session_key = ?",
                (session_key,),
            ).fetchone()
        return int((row["c"] if row else 0) or 0)

    def next_seq(self, session_key: str) -> int:
        with self._lock:
            meta = self._conn.execute(
                "SELECT next_seq FROM sessions WHERE key = ?",
                (session_key,),
            ).fetchone()
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq) + 1, 0) AS next_seq FROM messages WHERE session_key = ?",
                (session_key,),
            ).fetchone()
        from_messages = int((row["next_seq"] if row else 0) or 0)
        if meta is None:
            return from_messages
        return max(int(meta["next_seq"] or 0), from_messages)

    def insert_message(
        self,
        session_key: str,
        *,
        role: str,
        content: str,
        ts: str,
        seq: int,
        tool_chain: Any | None = None,
        extra: dict[str, Any] | None = None,
        thread_id: str | None = None,
        sender_role: str | None = None,
        media: list[str] | None = None,
        external_message_id: str | None = None,
        delivery_status: str | None = None,
    ) -> dict[str, Any]:
        message_id = f"{session_key}:{seq}"
        tool_chain_payload = (
            json.dumps(tool_chain, ensure_ascii=False)
            if tool_chain is not None
            else None
        )
        extra_payload = json.dumps(extra or {}, ensure_ascii=False)
        media_payload = (
            json.dumps(list(media), ensure_ascii=False) if media else None
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO messages (
                    id, session_key, seq, role, content, tool_chain, extra, ts,
                    thread_id, sender_role, media, external_message_id, delivery_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_key,
                    seq,
                    role,
                    content,
                    tool_chain_payload,
                    extra_payload,
                    ts,
                    thread_id,
                    sender_role,
                    media_payload,
                    external_message_id,
                    delivery_status,
                ),
            )
            self._conn.execute(
                """
                UPDATE sessions
                SET next_seq = CASE WHEN next_seq < ? THEN ? ELSE next_seq END
                WHERE key = ?
                """,
                (int(seq) + 1, int(seq) + 1, session_key),
            )
            self._conn.commit()
        row = {
            "id": message_id,
            "session_key": session_key,
            "seq": seq,
            "role": role,
            "content": content,
            "timestamp": ts,
        }
        if tool_chain is not None:
            row["tool_chain"] = tool_chain
        if thread_id:
            row["thread_id"] = thread_id
        if sender_role:
            row["sender_role"] = sender_role
        if media:
            row["media"] = list(media)
        if external_message_id:
            row["external_message_id"] = external_message_id
        if delivery_status:
            row["delivery_status"] = delivery_status
        if extra:
            row.update(extra)
        return row

    def replace_session_messages(
        self,
        session_key: str,
        *,
        rows: list[dict[str, Any]],
        updated_at: str,
        last_consolidated: int,
        next_seq: int,
    ) -> None:
        """Atomically replace one session's persisted message snapshot."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "DELETE FROM messages WHERE session_key = ?",
                    (session_key,),
                )
                for row in rows:
                    tool_chain = row.get("tool_chain")
                    extra = row.get("extra")
                    self._conn.execute(
                        """
                        INSERT INTO messages (
                            id, session_key, seq, role, content, tool_chain, extra, ts,
                            thread_id, sender_role, media, external_message_id, delivery_status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(row["id"]),
                            session_key,
                            int(row["seq"]),
                            str(row["role"]),
                            str(row["content"]),
                            (
                                json.dumps(tool_chain, ensure_ascii=False)
                                if tool_chain is not None
                                else None
                            ),
                            json.dumps(extra or {}, ensure_ascii=False),
                            str(row["timestamp"]),
                            str(row.get("thread_id") or "") or None,
                            str(row.get("sender_role") or "") or None,
                            (
                                json.dumps(list(row.get("media") or []), ensure_ascii=False)
                                if row.get("media")
                                else None
                            ),
                            str(row.get("external_message_id") or "") or None,
                            str(row.get("delivery_status") or "") or None,
                        ),
                    )
                self._conn.execute(
                    """
                    UPDATE sessions
                    SET updated_at = ?,
                        last_consolidated = ?,
                        next_seq = ?
                    WHERE key = ?
                    """,
                    (
                        updated_at,
                        int(last_consolidated),
                        max(0, int(next_seq)),
                        session_key,
                    ),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def fetch_session_messages(self, session_key: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT """ + _MESSAGE_SELECT_COLUMNS + """
                FROM messages
                WHERE session_key = ?
                ORDER BY seq ASC
                """,
                (session_key,),
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def list_messages_for_admin(
        self,
        *,
        session_key: str | None = None,
        q: str = "",
        role: str = "",
        page: int = 1,
        page_size: int = 25,
        sort_by: str = "ts",
        sort_order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), 200))
        offset = (safe_page - 1) * safe_page_size
        safe_sort = "ASC" if str(sort_order).lower() == "asc" else "DESC"
        safe_sort_by = (
            sort_by if sort_by in {"ts", "seq", "role", "session_key"} else "ts"
        )

        params: list[Any] = []
        where_parts: list[str] = []
        if session_key:
            where_parts.append("session_key = ?")
            params.append(session_key)
        term = (q or "").strip()
        if term:
            where_parts.append("content LIKE ?")
            params.append(f"%{term}%")
        if role:
            where_parts.append("role = ?")
            params.append(role)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        count_sql = f"SELECT COUNT(1) AS c FROM messages {where_sql}"
        data_sql = f"""
            SELECT {_MESSAGE_SELECT_COLUMNS}
            FROM messages
            {where_sql}
            ORDER BY {safe_sort_by} {safe_sort}, seq {safe_sort}, id ASC
            LIMIT ? OFFSET ?
        """
        with self._lock:
            count_row = self._conn.execute(count_sql, tuple(params)).fetchone()
            rows = self._conn.execute(
                data_sql,
                tuple([*params, safe_page_size, offset]),
            ).fetchall()
        total = int((count_row["c"] if count_row else 0) or 0)
        return [self._row_to_message(row) for row in rows], total

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                f"""
                SELECT {_MESSAGE_SELECT_COLUMNS}
                FROM messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

    def update_message(
        self,
        message_id: str,
        *,
        role: str | None = None,
        content: str | None = None,
        tool_chain: Any | None = None,
        extra: dict[str, Any] | None = None,
        ts: str | None = None,
        thread_id: str | None = None,
        sender_role: str | None = None,
        media: list[str] | None = None,
        external_message_id: str | None = None,
        delivery_status: str | None = None,
    ) -> dict[str, Any] | None:
        set_parts: list[str] = []
        params: list[Any] = []
        if role is not None:
            set_parts.append("role = ?")
            params.append(role)
        if content is not None:
            set_parts.append("content = ?")
            params.append(content)
        if tool_chain is not None:
            set_parts.append("tool_chain = ?")
            params.append(json.dumps(tool_chain, ensure_ascii=False))
        if extra is not None:
            set_parts.append("extra = ?")
            params.append(json.dumps(extra, ensure_ascii=False))
        if ts is not None:
            set_parts.append("ts = ?")
            params.append(ts)
        if thread_id is not None:
            set_parts.append("thread_id = ?")
            params.append(str(thread_id).strip() or None)
        if sender_role is not None:
            set_parts.append("sender_role = ?")
            params.append(str(sender_role).strip() or None)
        if media is not None:
            set_parts.append("media = ?")
            params.append(
                json.dumps(list(media), ensure_ascii=False) if media else None
            )
        if external_message_id is not None:
            set_parts.append("external_message_id = ?")
            params.append(str(external_message_id).strip() or None)
        if delivery_status is not None:
            set_parts.append("delivery_status = ?")
            params.append(str(delivery_status).strip() or None)
        if not set_parts:
            return self.get_message(message_id)

        with self._lock:
            row = self._conn.execute(
                "SELECT session_key FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                return None
            session_key = str(row["session_key"])
            params.append(message_id)
            cur = self._conn.execute(
                f"UPDATE messages SET {', '.join(set_parts)} WHERE id = ?",
                tuple(params),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE key = ?",
                (datetime.now().astimezone().isoformat(), session_key),
            )
            self._conn.commit()
        if cur.rowcount <= 0:
            return None
        return self.get_message(message_id)

    def replace_message_media(
        self,
        *,
        session_key: str,
        message_id: str,
        media_index: int,
        expected_path: str,
        new_path: str,
    ) -> dict[str, Any]:
        """Atomically replace one media slot when its authoritative path is unchanged."""

        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT session_key, media FROM messages WHERE id = ?",
                    (message_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"消息不存在: {message_id}")
                if str(row["session_key"]) != session_key:
                    raise ValueError("消息不属于指定会话")
                raw_media = row["media"]
                media = json.loads(raw_media) if raw_media else []
                if not isinstance(media, list) or media_index < 0 or media_index >= len(media):
                    raise ValueError("media_index 超出消息媒体范围")
                if str(media[media_index] or "") != expected_path:
                    raise ValueError("消息图片已发生变化，请刷新后重试")
                media[media_index] = new_path
                updated_at = datetime.now().astimezone().isoformat()
                self._conn.execute(
                    "UPDATE messages SET media = ? WHERE id = ?",
                    (json.dumps(media, ensure_ascii=False), message_id),
                )
                self._conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE key = ?",
                    (updated_at, session_key),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        updated = self.get_message(message_id)
        if updated is None:
            raise RuntimeError("消息媒体更新后无法重新读取")
        return updated

    def update_latest_assistant_delivery(
        self,
        session_key: str,
        *,
        thread_id: str = "",
        delivery_status: str,
        external_message_id: str = "",
    ) -> dict[str, Any] | None:
        clean_session_key = str(session_key or "").strip()
        clean_thread_id = str(thread_id or "").strip()
        clean_status = str(delivery_status or "").strip()
        clean_external_id = str(external_message_id or "").strip()
        if not clean_session_key or not clean_status:
            return None
        with self._lock:
            if clean_thread_id:
                row = self._conn.execute(
                    """
                    SELECT id
                    FROM messages
                    WHERE session_key = ?
                      AND role = 'assistant'
                      AND thread_id = ?
                    ORDER BY seq DESC
                    LIMIT 1
                    """,
                    (clean_session_key, clean_thread_id),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """
                    SELECT id
                    FROM messages
                    WHERE session_key = ?
                      AND role = 'assistant'
                    ORDER BY seq DESC
                    LIMIT 1
                    """,
                    (clean_session_key,),
                ).fetchone()
            if row is None:
                return None
            message_id = str(row["id"])
        return self.update_message(
            message_id,
            delivery_status=clean_status,
            external_message_id=clean_external_id or None,
        )

    def delete_message(self, message_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT session_key FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                return False
            session_key = str(row["session_key"])
            cur = self._conn.execute(
                "DELETE FROM messages WHERE id = ?",
                (message_id,),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE key = ?",
                (datetime.now().astimezone().isoformat(), session_key),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def delete_messages_batch(self, ids: list[str]) -> int:
        clean_ids = [
            str(message_id).strip() for message_id in ids if str(message_id).strip()
        ]
        if not clean_ids:
            return 0
        placeholders = ",".join("?" for _ in clean_ids)
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            rows = self._conn.execute(
                f"SELECT DISTINCT session_key FROM messages WHERE id IN ({placeholders})",
                tuple(clean_ids),
            ).fetchall()
            cur = self._conn.execute(
                f"DELETE FROM messages WHERE id IN ({placeholders})",
                tuple(clean_ids),
            )
            for row in rows:
                self._conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE key = ?",
                    (now, str(row["session_key"])),
                )
            self._conn.commit()
        return int(cur.rowcount or 0)
    def delete_session_messages_and_update_cursor(
        self,
        session_key: str,
        *,
        ids: list[str],
        last_consolidated: int,
    ) -> int:
        clean_ids = [
            str(message_id).strip() for message_id in ids if str(message_id).strip()
        ]
        if not clean_ids:
            return 0
        placeholders = ",".join("?" for _ in clean_ids)
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                seq_rows = self._conn.execute(
                    f"""
                    SELECT seq
                    FROM messages
                    WHERE session_key = ? AND id IN ({placeholders})
                    """,
                    tuple([session_key, *clean_ids]),
                ).fetchall()
                next_seq = (
                    max(int(row["seq"]) for row in seq_rows) + 1 if seq_rows else 0
                )
                cur = self._conn.execute(
                    f"""
                    DELETE FROM messages
                    WHERE session_key = ? AND id IN ({placeholders})
                    """,
                    tuple([session_key, *clean_ids]),
                )
                self._conn.execute(
                    """
                    UPDATE sessions
                    SET last_consolidated = ?,
                        updated_at = ?,
                        next_seq = CASE WHEN next_seq < ? THEN ? ELSE next_seq END
                    WHERE key = ?
                    """,
                    (int(last_consolidated), now, next_seq, next_seq, session_key),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return int(cur.rowcount or 0)
