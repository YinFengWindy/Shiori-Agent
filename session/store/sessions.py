"""Session 元数据与管理操作。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

class _SessionMixin:
    def session_exists(self, key: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM sessions WHERE key = ?", (key,)
            ).fetchone()
        return row is not None

    def upsert_session(
        self,
        key: str,
        *,
        created_at: str,
        updated_at: str,
        last_consolidated: int,
        metadata: dict[str, Any],
    ) -> None:
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (key, created_at, updated_at, last_consolidated, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    last_consolidated = excluded.last_consolidated,
                    metadata = excluded.metadata
                """,
                (key, created_at, updated_at, int(last_consolidated), payload),
            )
            self._conn.commit()

    def update_last_consolidated(self, key: str, last_consolidated: int) -> None:
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            self._conn.execute(
                """
                UPDATE sessions
                SET last_consolidated = ?, updated_at = ?
                WHERE key = ?
                """,
                (int(last_consolidated), now, key),
            )
            self._conn.commit()

    def get_session_meta(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT key, created_at, updated_at, last_consolidated, metadata, last_user_at, last_proactive_at FROM sessions WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return {
            "key": row["key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_consolidated": int(row["last_consolidated"] or 0),
            "metadata": json.loads(row["metadata"] or "{}"),
            "last_user_at": row["last_user_at"],
            "last_proactive_at": row["last_proactive_at"],
        }

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("""
                SELECT key, created_at, updated_at, last_user_at, last_proactive_at
                FROM sessions
                ORDER BY updated_at DESC
                """).fetchall()
        return [
            {
                "key": str(row["key"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_user_at": row["last_user_at"],
                "last_proactive_at": row["last_proactive_at"],
            }
            for row in rows
        ]

    def list_sessions_for_admin(
        self,
        *,
        q: str = "",
        channel: str = "",
        updated_from: str = "",
        updated_to: str = "",
        has_proactive: bool | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), 200))
        offset = (safe_page - 1) * safe_page_size
        safe_sort_by = (
            sort_by
            if sort_by
            in {
                "updated_at",
                "created_at",
                "last_user_at",
                "last_proactive_at",
            }
            else "updated_at"
        )
        safe_sort_order = "ASC" if str(sort_order).lower() == "asc" else "DESC"

        params: list[Any] = []
        where_parts: list[str] = []
        query = (q or "").strip()
        if query:
            where_parts.append("(s.key LIKE ? OR COALESCE(s.metadata, '') LIKE ?)")
            like = f"%{query}%"
            params.extend([like, like])
        if channel:
            where_parts.append("s.key LIKE ?")
            params.append(f"{channel}:%")
        if updated_from:
            where_parts.append("s.updated_at >= ?")
            params.append(updated_from)
        if updated_to:
            where_parts.append("s.updated_at <= ?")
            params.append(updated_to)
        if has_proactive is True:
            where_parts.append("s.last_proactive_at IS NOT NULL")
        if has_proactive is False:
            where_parts.append("s.last_proactive_at IS NULL")

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        count_sql = f"""
            SELECT COUNT(1) AS c
            FROM sessions s
            {where_sql}
        """
        data_sql = f"""
            SELECT
                s.key,
                s.created_at,
                s.updated_at,
                s.last_consolidated,
                s.metadata,
                s.last_user_at,
                s.last_proactive_at,
                COALESCE(msg.message_count, 0) AS message_count
            FROM sessions s
            LEFT JOIN (
                SELECT session_key, COUNT(1) AS message_count
                FROM messages
                GROUP BY session_key
            ) msg ON msg.session_key = s.key
            {where_sql}
            ORDER BY s.{safe_sort_by} {safe_sort_order}, s.key ASC
            LIMIT ? OFFSET ?
        """
        with self._lock:
            count_row = self._conn.execute(count_sql, tuple(params)).fetchone()
            rows = self._conn.execute(
                data_sql,
                tuple([*params, safe_page_size, offset]),
            ).fetchall()
        total = int((count_row["c"] if count_row else 0) or 0)
        return [
            {
                "key": str(row["key"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_consolidated": int(row["last_consolidated"] or 0),
                "metadata": json.loads(row["metadata"] or "{}"),
                "last_user_at": row["last_user_at"],
                "last_proactive_at": row["last_proactive_at"],
                "message_count": int(row["message_count"] or 0),
            }
            for row in rows
        ], total

    def create_session(
        self,
        *,
        key: str,
        metadata: dict[str, Any] | None = None,
        last_consolidated: int = 0,
        last_user_at: str | None = None,
        last_proactive_at: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().astimezone().isoformat()
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (
                    key,
                    created_at,
                    updated_at,
                    last_consolidated,
                    metadata,
                    last_user_at,
                    last_proactive_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    now,
                    now,
                    int(last_consolidated),
                    payload,
                    last_user_at,
                    last_proactive_at,
                ),
            )
            self._conn.commit()
        meta = self.get_session_meta(key)
        if meta is None:
            raise ValueError(f"session 创建失败: {key}")
        return meta

    def update_session(
        self,
        key: str,
        *,
        metadata: dict[str, Any] | None = None,
        last_consolidated: int | None = None,
        last_user_at: str | None = None,
        last_proactive_at: str | None = None,
    ) -> dict[str, Any] | None:
        set_parts = ["updated_at = ?"]
        params: list[Any] = [datetime.now().astimezone().isoformat()]
        if metadata is not None:
            set_parts.append("metadata = ?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        if last_consolidated is not None:
            set_parts.append("last_consolidated = ?")
            params.append(int(last_consolidated))
        if last_user_at is not None:
            set_parts.append("last_user_at = ?")
            params.append(last_user_at)
        if last_proactive_at is not None:
            set_parts.append("last_proactive_at = ?")
            params.append(last_proactive_at)
        params.append(key)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE sessions SET {', '.join(set_parts)} WHERE key = ?",
                tuple(params),
            )
            self._conn.commit()
        if cur.rowcount <= 0:
            return None
        return self.get_session_meta(key)

    def delete_session(self, key: str, *, cascade: bool = False) -> bool:
        with self._lock:
            if not cascade:
                row = self._conn.execute(
                    "SELECT COUNT(1) AS c FROM messages WHERE session_key = ?",
                    (key,),
                ).fetchone()
                count = int((row["c"] if row else 0) or 0)
                if count > 0:
                    raise ValueError("session 下仍有 messages，需使用 cascade 删除")
            else:
                self._conn.execute(
                    "DELETE FROM messages WHERE session_key = ?",
                    (key,),
                )
            cur = self._conn.execute(
                "DELETE FROM sessions WHERE key = ?",
                (key,),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def delete_sessions_batch(self, keys: list[str], *, cascade: bool = False) -> int:
        clean_keys = [str(key).strip() for key in keys if str(key).strip()]
        if not clean_keys:
            return 0
        placeholders = ",".join("?" for _ in clean_keys)
        with self._lock:
            if not cascade:
                row = self._conn.execute(
                    f"""
                    SELECT COUNT(1) AS c
                    FROM messages
                    WHERE session_key IN ({placeholders})
                    """,
                    tuple(clean_keys),
                ).fetchone()
                count = int((row["c"] if row else 0) or 0)
                if count > 0:
                    raise ValueError(
                        "选中的 session 中仍有 messages，需使用 cascade 删除"
                    )
            else:
                self._conn.execute(
                    f"DELETE FROM messages WHERE session_key IN ({placeholders})",
                    tuple(clean_keys),
                )
            cur = self._conn.execute(
                f"DELETE FROM sessions WHERE key IN ({placeholders})",
                tuple(clean_keys),
            )
            self._conn.commit()
        return int(cur.rowcount or 0)
