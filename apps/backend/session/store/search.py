"""Session 消息搜索与上下文读取。"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .common import _MESSAGE_SELECT_COLUMNS

class _SearchMixin:
    def fetch_by_ids_with_context(
        self, ids: list[str], context: int
    ) -> list[dict[str, Any]]:
        """Fetch messages by ID, expanding each hit by ±context rows in its session.

        Returns messages ordered by (session_key, seq).
        Each dict includes ``in_source_ref: bool`` to distinguish hits from context.
        """
        if not ids:
            return []
        if context == 0:
            result = self.fetch_by_ids(ids)
            for m in result:
                m["in_source_ref"] = True
            return result

        id_set = set(ids)
        session_seqs: dict[str, set[int]] = {}
        for msg_id in ids:
            parts = msg_id.rsplit(":", 1)
            if len(parts) != 2:
                continue
            sk, seq_str = parts
            try:
                seq = int(seq_str)
            except ValueError:
                continue
            if sk not in session_seqs:
                session_seqs[sk] = set()
            session_seqs[sk].add(seq)

        if not session_seqs:
            return []

        results: list[dict[str, Any]] = []
        with self._lock:
            for sk, seqs in session_seqs.items():
                expanded: set[int] = set()
                for seq in seqs:
                    for s in range(max(0, seq - context), seq + context + 1):
                        expanded.add(s)
                placeholders = ",".join("?" * len(expanded))
                rows = self._conn.execute(
                    f"SELECT {_MESSAGE_SELECT_COLUMNS} "
                    f"FROM messages WHERE session_key = ? AND seq IN ({placeholders}) ORDER BY seq",
                    [sk, *expanded],
                ).fetchall()
                for row in rows:
                    msg = self._row_to_message(row)
                    msg["in_source_ref"] = msg["id"] in id_set
                    results.append(msg)
        return results

    def fetch_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        order_expr = " ".join(f"WHEN ? THEN {i}" for i in range(len(ids)))
        sql = (
            f"SELECT {_MESSAGE_SELECT_COLUMNS} FROM messages "
            f"WHERE id IN ({placeholders}) ORDER BY CASE id {order_expr} END"
        )
        with self._lock:
            rows = self._conn.execute(sql, tuple(ids + ids)).fetchall()
        return [self._row_to_message(row) for row in rows]

    def fetch_message_around(
        self,
        message_id: str,
        *,
        context: int = 5,
    ) -> dict[str, Any]:
        """Fetch a message and nearby persisted messages by its real id."""
        safe_context = max(0, min(int(context), 100))
        with self._lock:
            target = self._conn.execute(
                f"SELECT {_MESSAGE_SELECT_COLUMNS} FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if target is None:
                return {
                    "messages": [],
                    "target_message_id": message_id,
                    "has_more_before": False,
                    "has_more_after": False,
                    "total_count": 0,
                }
            session_key = str(target["session_key"])
            target_seq = int(target["seq"])
            before_rows = self._conn.execute(
                f"""
                SELECT {_MESSAGE_SELECT_COLUMNS}
                FROM messages
                WHERE session_key = ? AND seq < ?
                ORDER BY seq DESC LIMIT ?
                """,
                (session_key, target_seq, safe_context),
            ).fetchall()
            after_rows = self._conn.execute(
                f"""
                SELECT {_MESSAGE_SELECT_COLUMNS}
                FROM messages
                WHERE session_key = ? AND seq > ?
                ORDER BY seq ASC LIMIT ?
                """,
                (session_key, target_seq, safe_context),
            ).fetchall()
            rows = [*reversed(before_rows), target, *after_rows]
            stats = self._conn.execute(
                """
                SELECT COUNT(1) AS total_count, MIN(seq) AS oldest_seq, MAX(seq) AS newest_seq
                FROM messages WHERE session_key = ?
                """,
                (session_key,),
            ).fetchone()
        messages = [self._row_to_message(row) for row in rows]
        for message in messages:
            message["is_target"] = message["id"] == message_id
        oldest_seq = stats["oldest_seq"] if stats else None
        newest_seq = stats["newest_seq"] if stats else None
        return {
            "messages": messages,
            "target_message_id": message_id,
            "session_key": session_key,
            "has_more_before": (
                bool(
                    oldest_seq is not None
                    and messages
                    and messages[0]["seq"] > int(oldest_seq)
                )
            ),
            "has_more_after": (
                bool(
                    newest_seq is not None
                    and messages
                    and messages[-1]["seq"] < int(newest_seq)
                )
            ),
            "oldest_seq": int(oldest_seq) if oldest_seq is not None else None,
            "newest_seq": int(newest_seq) if newest_seq is not None else None,
            "total_count": int((stats["total_count"] if stats else 0) or 0),
            "context": safe_context,
        }

    def search_messages(
        self,
        query: str,
        *,
        session_key: str | None = None,
        role: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        params: list[Any] = []
        where_parts: list[str] = []
        if session_key:
            where_parts.append("m.session_key = ?")
            params.append(session_key)
        if role:
            where_parts.append("m.role = ?")
            params.append(role)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # Split into individual terms for both FTS and LIKE paths.
        terms = [t for t in query.split() if t]
        if not terms:
            terms = [query]

        term_conditions_or = " OR ".join("m.content LIKE ?" for _ in terms)
        score_expr = " + ".join(
            "(CASE WHEN m.content LIKE ? THEN 1 ELSE 0 END)" for _ in terms
        )
        if self._has_fts:
            # 长词走 FTS，短词继续走 LIKE，再把两路结果合并去重。
            fts_terms = [t for t in terms if len(t) >= 3]
            if fts_terms:
                fts_query = " OR ".join(fts_terms)
                connector = "AND" if where_sql else "WHERE"
                count_params = [fts_query] + params[:]
                count_sql = (
                    "SELECT COUNT(1) AS c "
                    "FROM messages m "
                    "LEFT JOIN ("
                    "    SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?"
                    ") fts ON m.rowid = fts.rowid "
                    f"{where_sql} {connector} (fts.rowid IS NOT NULL OR ({term_conditions_or})) "
                )
                count_params.extend(f"%{t}%" for t in terms)
                fts_params: list[Any] = []
                fts_sql = (
                    "SELECT m.id, m.session_key, m.seq, m.role, m.content, m.tool_chain, m.extra, m.ts, "
                    "m.thread_id, m.sender_role, m.media, m.external_message_id, m.delivery_status, "
                    f"({score_expr}) AS match_score, "
                    "fts.rank_score AS rank_score "
                    "FROM messages m "
                    "LEFT JOIN ("
                    "    SELECT rowid, bm25(messages_fts) AS rank_score "
                    "    FROM messages_fts WHERE messages_fts MATCH ?"
                    ") fts ON m.rowid = fts.rowid "
                    f"{where_sql} {connector} (fts.rowid IS NOT NULL OR ({term_conditions_or})) "
                    "ORDER BY match_score DESC, "
                    "CASE WHEN rank_score IS NULL THEN 1 ELSE 0 END ASC, "
                    "rank_score ASC, m.seq DESC LIMIT ? OFFSET ?"
                )
                fts_params.extend(f"%{t}%" for t in terms)
                fts_params.append(fts_query)
                fts_params.extend(params[:])
                fts_params.extend(f"%{t}%" for t in terms)
                fts_params.extend([limit, offset])
                try:
                    with self._lock:
                        count_row = self._conn.execute(
                            count_sql, tuple(count_params)
                        ).fetchone()
                        rows = self._conn.execute(fts_sql, tuple(fts_params)).fetchall()
                    total = int((count_row["c"] if count_row else 0) or 0)
                    return [self._row_to_message(row) for row in rows], total
                except sqlite3.OperationalError:
                    pass

        # LIKE fallback: OR across all terms so any hit surfaces; rank by match count descending.
        like_params: list[Any] = []
        count_params = params[:]
        connector = "AND" if where_sql else "WHERE"
        count_sql = f"SELECT COUNT(1) AS c FROM messages m {where_sql} {connector} ({term_conditions_or}) "
        count_params.extend(f"%{t}%" for t in terms)
        like_sql = (
            f"SELECT m.id, m.session_key, m.seq, m.role, m.content, m.tool_chain, m.extra, m.ts, "
            "m.thread_id, m.sender_role, m.media, m.external_message_id, m.delivery_status, "
            f"({score_expr}) AS match_score "
            f"FROM messages m {where_sql} {connector} ({term_conditions_or}) "
            f"ORDER BY match_score DESC, m.seq DESC LIMIT ? OFFSET ?"
        )
        # score_expr binds: one %t% per term; term_conditions_or binds: one %t% per term
        like_params.extend(f"%{t}%" for t in terms)  # for score_expr
        like_params.extend(params)
        like_params.extend(f"%{t}%" for t in terms)  # for WHERE OR
        like_params.extend([limit, offset])
        with self._lock:
            count_row = self._conn.execute(count_sql, tuple(count_params)).fetchone()
            rows = self._conn.execute(like_sql, tuple(like_params)).fetchall()
        total = int((count_row["c"] if count_row else 0) or 0)
        return [self._row_to_message(row) for row in rows], total

    def search_message_previews(
        self,
        query: str,
        *,
        session_key: str | None = None,
        role: str | None = None,
        limit: int = 20,
        offset: int = 0,
        preview_length: int = 240,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search messages for desktop navigation without returning heavy fields."""
        messages, total = self.search_messages(
            query,
            session_key=session_key,
            role=role,
            limit=limit,
            offset=offset,
        )
        safe_length = max(40, min(int(preview_length), 1000))
        previews: list[dict[str, Any]] = []
        for message in messages:
            content = str(message.get("content") or "")
            previews.append(
                {
                    "id": message.get("id"),
                    "session_key": message.get("session_key"),
                    "seq": message.get("seq"),
                    "role": message.get("role"),
                    "preview": content[:safe_length]
                    + ("..." if len(content) > safe_length else ""),
                    "timestamp": message.get("timestamp"),
                }
            )
        return previews, total

    def _row_to_message(self, row: sqlite3.Row) -> dict[str, Any]:
        row_keys = set(row.keys())
        message: dict[str, Any] = {
            "id": row["id"],
            "session_key": row["session_key"],
            "seq": int(row["seq"]),
            "role": row["role"],
            "content": row["content"] or "",
            "timestamp": row["ts"],
        }
        tool_chain = row["tool_chain"]
        if tool_chain:
            message["tool_chain"] = json.loads(tool_chain)
        if "thread_id" in row_keys and str(row["thread_id"] or "").strip():
            message["thread_id"] = str(row["thread_id"]).strip()
        if "sender_role" in row_keys and str(row["sender_role"] or "").strip():
            message["sender_role"] = str(row["sender_role"]).strip()
        if "media" in row_keys and row["media"]:
            raw_media = json.loads(row["media"] or "[]")
            if isinstance(raw_media, list):
                message["media"] = raw_media
        if (
            "external_message_id" in row_keys
            and str(row["external_message_id"] or "").strip()
        ):
            message["external_message_id"] = str(row["external_message_id"]).strip()
        if "delivery_status" in row_keys and str(row["delivery_status"] or "").strip():
            message["delivery_status"] = str(row["delivery_status"]).strip()
        extra = json.loads(row["extra"] or "{}")
        if extra:
            message.update(extra)
        return message
