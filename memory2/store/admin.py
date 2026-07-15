"""Memory v2 管理端查询与 CRUD 操作。"""

from __future__ import annotations

import json

from .common import (
    _coerce_emotional_weight,
    _domain_json_filter,
    _now_iso,
    _role_json_filter,
)


class _StoreAdminMixin:
    def list_items_for_admin(
        self,
        *,
        q: str = "",
        memory_type: str = "",
        memory_domain: str = "",
        status: str = "",
        source_ref: str = "",
        role_id: str = "",
        scope_channel: str = "",
        scope_chat_id: str = "",
        has_embedding: bool | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict[str, object]], int]:
        with self._lock:
            safe_sort_by = sort_by if sort_by in {
                "updated_at",
                "created_at",
                "happened_at",
                "reinforcement",
                "emotional_weight",
                "memory_type",
            } else "created_at"
            safe_sort_order = "asc" if sort_order == "asc" else "desc"
            safe_page = max(1, page)
            safe_page_size = max(1, min(page_size, 200))
            offset = (safe_page - 1) * safe_page_size

            where_parts = ["1=1"]
            params: list[object] = []

            if q:
                where_parts.append("(id LIKE ? OR summary LIKE ? OR COALESCE(source_ref, '') LIKE ?)")
                like = f"%{q}%"
                params.extend([like, like, like])
            if memory_type:
                where_parts.append("memory_type = ?")
                params.append(memory_type)
            if memory_domain:
                where_parts.append(_domain_json_filter())
                params.append(memory_domain.strip())
            if status:
                where_parts.append("status = ?")
                params.append(status)
            if source_ref:
                where_parts.append("COALESCE(source_ref, '') LIKE ?")
                params.append(f"%{source_ref}%")
            if role_id:
                where_parts.append(_role_json_filter())
                params.append(role_id.strip())
            if scope_channel:
                where_parts.append(
                    "COALESCE(TRIM(json_extract(extra_json, '$.scope_channel')), '') = ?"
                )
                params.append(scope_channel.strip())
            if scope_chat_id:
                where_parts.append(
                    "COALESCE(TRIM(json_extract(extra_json, '$.scope_chat_id')), '') = ?"
                )
                params.append(scope_chat_id.strip())
            if has_embedding is True:
                where_parts.append("embedding IS NOT NULL")
            elif has_embedding is False:
                where_parts.append("embedding IS NULL")

            where_sql = " AND ".join(where_parts)
            total = int(
                self._db.execute(
                    f"SELECT COUNT(*) FROM memory_items WHERE {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = self._db.execute(
                f"""
                SELECT id, memory_type, summary, source_ref, happened_at, status,
                       created_at, updated_at, reinforcement, emotional_weight,
                       extra_json, embedding IS NOT NULL
                FROM memory_items
                WHERE {where_sql}
                ORDER BY {safe_sort_by} {safe_sort_order}, id ASC
                LIMIT ? OFFSET ?
                """,
                tuple([*params, safe_page_size, offset]),
            ).fetchall()
            items: list[dict[str, object]] = []
            for row in rows:
                (
                    row_id,
                    row_memory_type,
                    summary,
                    row_source_ref,
                    happened_at,
                    row_status,
                    created_at,
                    updated_at,
                    reinforcement,
                    emotional_weight,
                    extra_json,
                    row_has_embedding,
                ) = row
                extra = json.loads(extra_json) if extra_json else {}
                items.append(
                    {
                        "id": str(row_id),
                    "memory_type": row_memory_type,
                    "memory_domain": str(extra.get("memory_domain", "") or ""),
                    "summary": summary,
                        "source_ref": row_source_ref,
                        "happened_at": happened_at,
                        "status": row_status,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "reinforcement": reinforcement,
                        "emotional_weight": emotional_weight,
                        "has_embedding": bool(row_has_embedding),
                        "scope_channel": extra.get("scope_channel", ""),
                        "scope_chat_id": extra.get("scope_chat_id", ""),
                    }
                )
            return items, total

    def get_item_for_admin(
        self,
        item_id: str,
        *,
        include_embedding: bool = False,
    ) -> dict[str, object] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id, memory_type, summary, content_hash, embedding, reinforcement, "
                "emotional_weight, extra_json, source_ref, happened_at, status, created_at, updated_at "
                "FROM memory_items WHERE id=?",
                (item_id,),
            ).fetchone()
        if row is None:
            return None
        (
            row_id,
            memory_type,
            summary,
            content_hash,
            embedding_json,
            reinforcement,
            emotional_weight,
            extra_json,
            source_ref,
            happened_at,
            status,
            created_at,
            updated_at,
        ) = row
        embedding = json.loads(embedding_json) if embedding_json else None
        extra = json.loads(extra_json) if extra_json else {}
        return {
            "id": row_id,
            "memory_type": memory_type,
            "memory_domain": str(extra.get("memory_domain", "") or ""),
            "summary": summary,
            "content_hash": content_hash,
            "reinforcement": reinforcement,
            "emotional_weight": emotional_weight,
            "extra_json": extra,
            "role_id": str(extra.get("role_id", "") or ""),
            "source_ref": source_ref,
            "happened_at": happened_at,
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
            "has_embedding": embedding is not None,
            "embedding_dim": len(embedding) if embedding is not None else 0,
            "embedding": embedding if include_embedding else None,
        }

    def update_item_for_admin(
        self,
        item_id: str,
        *,
        status: str | None = None,
        extra_json: dict[str, object] | None = None,
        source_ref: str | None = None,
        happened_at: str | None = None,
        emotional_weight: int | None = None,
    ) -> dict[str, object] | None:
        with self._lock:
            updates: list[str] = []
            params: list[object] = []

            if status is not None:
                safe_status = status.strip()
                if safe_status not in {"active", "superseded"}:
                    raise ValueError("status 仅支持 active 或 superseded")
                updates.append("status=?")
                params.append(safe_status)
            if extra_json is not None:
                updates.append("extra_json=?")
                params.append(json.dumps(extra_json, ensure_ascii=False))
            if source_ref is not None:
                updates.append("source_ref=?")
                params.append(source_ref)
            if happened_at is not None:
                updates.append("happened_at=?")
                params.append(happened_at)
            if emotional_weight is not None:
                updates.append("emotional_weight=?")
                params.append(_coerce_emotional_weight(emotional_weight))
            if not updates:
                return self.get_item_for_admin(item_id)

            updates.append("updated_at=?")
            params.append(_now_iso())
            params.append(item_id)
            cur = self._db.execute(
                f"UPDATE memory_items SET {', '.join(updates)} WHERE id=?",
                params,
            )
            self._db.commit()
            if cur.rowcount <= 0:
                return None
        return self.get_item_for_admin(item_id)

    def delete_item(self, item_id: str) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT rowid FROM memory_items WHERE id=?",
                (item_id,),
            ).fetchone()
            if row is None:
                return False
            cur = self._db.execute(
                "DELETE FROM memory_items WHERE id=?",
                (item_id,),
            )
            self._vec_delete([row[0]])
            self._db.commit()
            return cur.rowcount > 0

    def delete_items_batch(self, ids: list[str]) -> int:
        if not ids:
            return 0
        with self._lock:
            placeholders = ",".join("?" for _ in ids)
            rowids = [
                r[0]
                for r in self._db.execute(
                    f"SELECT rowid FROM memory_items WHERE id IN ({placeholders})",
                    ids,
                ).fetchall()
            ]
            cur = self._db.execute(
                f"DELETE FROM memory_items WHERE id IN ({placeholders})",
                ids,
            )
            self._vec_delete(rowids)
            self._db.commit()
            return int(cur.rowcount or 0)

    def find_similar_items_for_admin(
        self,
        item_id: str,
        *,
        top_k: int = 8,
        memory_type: str = "",
        score_threshold: float = 0.0,
        include_superseded: bool = False,
    ) -> list[dict[str, object]]:
        base = self.get_item_for_admin(item_id, include_embedding=True)
        if base is None:
            raise KeyError(item_id)
        embedding = base.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("memory 没有 embedding")

        results = self.vector_search(
            query_vec=embedding,
            top_k=max(1, top_k) + 1,
            memory_types=[memory_type] if memory_type else None,
            score_threshold=score_threshold,
            include_superseded=include_superseded,
        )
        filtered = [item for item in results if item.get("id") != item_id]
        return filtered[: max(1, top_k)]
