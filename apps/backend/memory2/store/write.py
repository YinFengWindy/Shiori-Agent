"""Memory v2 核心写入、替换与合并操作。"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time

from .common import (
    _coerce_emotional_weight,
    _content_hash,
    _now_iso,
)

logger = logging.getLogger(__name__)


class _StoreWriteMixin:
    def upsert_item(
        self,
        memory_type: str,
        summary: str,
        embedding: list[float] | None,
        source_ref: str | None = None,
        extra: dict[str, object] | None = None,
        happened_at: str | None = None,
        emotional_weight: int = 0,
    ) -> str:
        """写入或强化一条记忆。返回 'new:id' 或 'reinforced:id'"""
        chash = _content_hash(summary, memory_type)
        emotional_weight = _coerce_emotional_weight(emotional_weight)
        existing = self._db.execute(
            "SELECT id, status FROM memory_items WHERE content_hash=? AND memory_type=?",
            (chash, memory_type),
        ).fetchone()
        if existing:
            row_id, status = existing
            if status == "superseded":
                self._db.execute(
                    "UPDATE memory_items SET status='active', reinforcement=reinforcement+1, updated_at=?, emotional_weight=MAX(emotional_weight, ?) WHERE id=?",
                    (_now_iso(), emotional_weight, row_id),
                )
            else:
                self._db.execute(
                    "UPDATE memory_items SET reinforcement=reinforcement+1, updated_at=?, emotional_weight=MAX(emotional_weight, ?) WHERE id=?",
                    (_now_iso(), emotional_weight, row_id),
                )
            self._db.commit()
            return f"reinforced:{row_id}"

        item_id = hashlib.md5(f"{chash}{time.time()}".encode()).hexdigest()[:12]
        cur = self._db.execute(
            """INSERT INTO memory_items
               (id, memory_type, summary, content_hash, embedding, emotional_weight,
                extra_json, source_ref, happened_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id,
                memory_type,
                summary,
                chash,
                json.dumps(embedding) if embedding is not None else None,
                emotional_weight,
                json.dumps(extra) if extra else None,
                source_ref,
                happened_at,
                _now_iso(),
                _now_iso(),
            ),
        )
        item_rowid = cur.lastrowid
        self._db.commit()

        if embedding is not None and item_rowid is not None:
            self._vec_insert(item_rowid, embedding)
            self._db.commit()

        return f"new:{item_id}"

    def upsert_consolidation_event(
        self,
        *,
        source_ref: str,
        summary: str,
        embedding: list[float] | None,
        extra: dict[str, object] | None = None,
        happened_at: str | None = None,
        emotional_weight: int = 0,
    ) -> str:
        """原子写入 consolidation event：同一 source_ref 最多写一次。"""
        src = (source_ref or "").strip()
        text = (summary or "").strip()
        if not src or not text:
            return "skipped:empty"
        emotional_weight = _coerce_emotional_weight(emotional_weight)

        self._db.execute("BEGIN IMMEDIATE")
        new_item_rowid: int | None = None
        new_item_emb: list[float] | None = None
        try:
            already = self._db.execute(
                "SELECT item_id FROM consolidation_events WHERE source_ref=?",
                (src,),
            ).fetchone()
            if already is not None:
                self._db.execute("COMMIT")
                existing_id = already[0] or ""
                return f"skipped:{existing_id or src}"

            chash = _content_hash(text, "event")
            existing = self._db.execute(
                "SELECT id, status FROM memory_items WHERE content_hash=? AND memory_type=?",
                (chash, "event"),
            ).fetchone()

            if existing:
                row_id, status = existing
                if status == "superseded":
                    self._db.execute(
                        "UPDATE memory_items SET status='active', reinforcement=reinforcement+1, updated_at=?, emotional_weight=MAX(emotional_weight, ?), happened_at=COALESCE(NULLIF(happened_at, ''), ?) WHERE id=?",
                        (_now_iso(), emotional_weight, happened_at, row_id),
                    )
                else:
                    self._db.execute(
                        "UPDATE memory_items SET reinforcement=reinforcement+1, updated_at=?, emotional_weight=MAX(emotional_weight, ?), happened_at=COALESCE(NULLIF(happened_at, ''), ?) WHERE id=?",
                        (_now_iso(), emotional_weight, happened_at, row_id),
                    )
                item_id = row_id
                result = f"reinforced:{row_id}"
            else:
                item_id = hashlib.md5(f"{chash}{time.time()}".encode()).hexdigest()[:12]
                cur = self._db.execute(
                    """INSERT INTO memory_items
                       (id, memory_type, summary, content_hash, embedding, emotional_weight,
                        extra_json, source_ref, happened_at, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item_id,
                        "event",
                        text,
                        chash,
                        json.dumps(embedding) if embedding is not None else None,
                        emotional_weight,
                        json.dumps(extra) if extra else None,
                        src,
                        happened_at,
                        _now_iso(),
                        _now_iso(),
                    ),
                )
                new_item_rowid = cur.lastrowid
                new_item_emb = embedding
                result = f"new:{item_id}"

            self._db.execute(
                "INSERT INTO consolidation_events(source_ref, item_id, created_at) VALUES (?, ?, ?)",
                (src, item_id, _now_iso()),
            )
            self._db.execute("COMMIT")

            if new_item_rowid is not None and new_item_emb is not None:
                self._vec_insert(new_item_rowid, new_item_emb)
                self._db.commit()

            return result
        except Exception:
            try:
                self._db.execute("ROLLBACK")
            except Exception:
                pass
            raise

    def has_consolidation_source_ref(self, source_ref: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM consolidation_events WHERE source_ref=? LIMIT 1",
            ((source_ref or "").strip(),),
        ).fetchone()
        return row is not None

    def mark_superseded(self, item_id: str) -> None:
        """将指定条目标记为已退休。"""
        self._db.execute(
            "UPDATE memory_items SET status='superseded', updated_at=? WHERE id=?",
            (_now_iso(), item_id),
        )
        self._db.commit()

    def mark_superseded_batch(self, ids: list[str]) -> None:
        if not ids:
            return
        now = _now_iso()
        self._db.executemany(
            "UPDATE memory_items SET status='superseded', updated_at=? WHERE id=?",
            [(now, item_id) for item_id in ids],
        )
        self._db.commit()

    def get_items_by_ids(self, ids: list[str]) -> list[dict[str, object]]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._db.execute(
            "SELECT id, memory_type, summary, extra_json, source_ref, happened_at, "
            "status, created_at, updated_at, emotional_weight "
            f"FROM memory_items WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        by_id: dict[str, dict[str, object]] = {}
        for (
            row_id,
            memory_type,
            summary,
            extra_json,
            source_ref,
            happened_at,
            status,
            created_at,
            updated_at,
            emotional_weight,
        ) in rows:
            by_id[str(row_id)] = {
                "id": row_id,
                "memory_type": memory_type,
                "summary": summary,
                "extra_json": json.loads(extra_json) if extra_json else {},
                "source_ref": source_ref,
                "happened_at": happened_at,
                "status": status,
                "created_at": created_at,
                "updated_at": updated_at,
                "emotional_weight": emotional_weight,
            }
        return [by_id[item_id] for item_id in ids if item_id in by_id]

    def record_replacements(
        self,
        *,
        old_items: list[dict[str, object]],
        new_item: dict[str, object],
        source_ref: str | None = None,
        relation_type: str = "supersede",
    ) -> int:
        if not old_items or not new_item or not new_item.get("id"):
            return 0
        now = _now_iso()
        rows = []
        for old_item in old_items:
            if not old_item or not old_item.get("id"):
                continue
            rows.append(
                (
                    str(old_item.get("id")),
                    str(old_item.get("memory_type") or ""),
                    str(old_item.get("summary") or ""),
                    old_item.get("source_ref"),
                    old_item.get("happened_at"),
                    json.dumps(old_item.get("extra_json") or {}, ensure_ascii=False),
                    str(new_item.get("id")),
                    str(new_item.get("memory_type") or ""),
                    str(new_item.get("summary") or ""),
                    new_item.get("source_ref"),
                    new_item.get("happened_at"),
                    json.dumps(new_item.get("extra_json") or {}, ensure_ascii=False),
                    relation_type,
                    source_ref or new_item.get("source_ref"),
                    now,
                )
            )
        if not rows:
            return 0
        self._db.executemany(
            """INSERT INTO memory_replacements
               (old_item_id, old_memory_type, old_summary, old_source_ref, old_happened_at,
                old_extra_json, new_item_id, new_memory_type, new_summary, new_source_ref,
                new_happened_at, new_extra_json, relation_type, source_ref, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self._db.commit()
        return len(rows)

    def list_replacements(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT old_item_id, old_memory_type, old_summary, old_source_ref, "
            "old_happened_at, old_extra_json, new_item_id, new_memory_type, "
            "new_summary, new_source_ref, new_happened_at, new_extra_json, "
            "relation_type, source_ref, created_at "
            "FROM memory_replacements ORDER BY id ASC"
        ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "old_item_id": row[0],
                    "old_memory_type": row[1],
                    "old_summary": row[2],
                    "old_source_ref": row[3],
                    "old_happened_at": row[4],
                    "old_extra_json": json.loads(row[5]) if row[5] else {},
                    "new_item_id": row[6],
                    "new_memory_type": row[7],
                    "new_summary": row[8],
                    "new_source_ref": row[9],
                    "new_happened_at": row[10],
                    "new_extra_json": json.loads(row[11]) if row[11] else {},
                    "relation_type": row[12],
                    "source_ref": row[13],
                    "created_at": row[14],
                }
            )
        return result

    def reinforce_items_batch(self, ids: list[str], emotional_weight: int = 0) -> None:
        if not ids:
            return
        now = _now_iso()
        emotional_weight = _coerce_emotional_weight(emotional_weight)
        self._db.executemany(
            "UPDATE memory_items SET reinforcement=reinforcement+1, updated_at=?, emotional_weight=MAX(emotional_weight, ?) WHERE id=?",
            [(now, emotional_weight, item_id) for item_id in ids],
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # 读操作
    # ------------------------------------------------------------------

    def merge_item_raw(
        self,
        item_id: str,
        new_summary: str,
        new_hash: str,
        new_embedding: list[float],
        new_extra: dict[str, object] | None = None,
    ) -> None:
        """原子更新 merge 目标：summary + content_hash + embedding + reinforcement。
        new_extra 若提供则同步更新 extra_json。
        若 content_hash 冲突（极低概率），则 supersede 旧条目并由 upsert_item 写入新摘要。
        """
        try:
            if new_extra is not None:
                self._db.execute(
                    """UPDATE memory_items
                       SET summary=?, content_hash=?, embedding=?, extra_json=?,
                           reinforcement=reinforcement+1, updated_at=?
                       WHERE id=?""",
                    (
                        new_summary, new_hash, json.dumps(new_embedding),
                        json.dumps(new_extra), _now_iso(), item_id,
                    ),
                )
            else:
                self._db.execute(
                    """UPDATE memory_items
                       SET summary=?, content_hash=?, embedding=?,
                           reinforcement=reinforcement+1, updated_at=?
                       WHERE id=?""",
                    (new_summary, new_hash, json.dumps(new_embedding), _now_iso(), item_id),
                )
            self._db.commit()

            # 同步更新 vec_items（embedding 变了）
            if self._vec_enabled:
                row = self._db.execute(
                    "SELECT rowid FROM memory_items WHERE id=?", (item_id,)
                ).fetchone()
                if row:
                    self._vec_insert(row[0], new_embedding)
                    self._db.commit()

        except sqlite3.IntegrityError:
            # content_hash 撞上库中已有条目（极低概率）
            # 安全降级：supersede 旧条目，让 upsert_item 走 reinforce 路径
            logger.warning(
                "merge_item_raw: content_hash collision for item %s, "
                "superseding and falling back to upsert",
                item_id,
            )
            try:
                self._db.execute("ROLLBACK")
            except Exception:
                pass
            row = self._db.execute(
                "SELECT memory_type FROM memory_items WHERE id=?", (item_id,)
            ).fetchone()
            if row:
                self.mark_superseded(item_id)
                self.upsert_item(
                    memory_type=row[0],
                    summary=new_summary,
                    embedding=new_embedding,
                )

    def list_by_type(self, memory_type: str) -> list[dict[str, object]]:
        rows = self._db.execute(
            "SELECT id, memory_type, summary, extra_json, happened_at, reinforcement, emotional_weight "
            "FROM memory_items WHERE memory_type=?",
            (memory_type,),
        ).fetchall()
        result = []
        for row_id, mtype, summary, extra_json, happened_at, reinforcement, emotional_weight in rows:
            result.append(
                {
                    "id": row_id,
                    "memory_type": mtype,
                    "summary": summary,
                    "extra_json": json.loads(extra_json) if extra_json else {},
                    "happened_at": happened_at,
                    "reinforcement": reinforcement,
                    "emotional_weight": emotional_weight,
                }
            )
        return result
