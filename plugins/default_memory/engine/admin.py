"""默认记忆引擎的管理与撤销操作。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from memory2.store import MemoryStore2


def _source_ref_message_ids(source_ref: str) -> list[str]:
    raw = str(source_ref or "").strip()
    if not raw:
        return []
    base = raw.split("#", 1)[0].strip()
    if not base.startswith("["):
        return []
    try:
        loaded: object = json.loads(base)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    values: list[str] = []
    for item in cast(list[object], loaded):
        text = str(item).strip()
        if text:
            values.append(text)
    return values


def _undo_store_by_message_sources(
    store: MemoryStore2,
    message_ids: list[str],
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    clean_ids = [str(item).strip() for item in message_ids if str(item).strip()]
    if not clean_ids:
        return {"affected_ids": [], "restored_ids": [], "rollback_source_ids": []}
    target_ids = set(clean_ids)
    with store._lock:
        rows = store._db.execute("""
            SELECT id, source_ref
            FROM memory_items
            WHERE COALESCE(source_ref, '') != ''
            """).fetchall()
        affected_ids: set[str] = set()
        rollback_source_ids: set[str] = set()
        for item_id, source_ref in rows:
            source = str(source_ref or "").strip()
            base_ids = _source_ref_message_ids(source)
            if source in target_ids:
                affected_ids.add(str(item_id))
                rollback_source_ids.add(source)
                continue
            if base_ids and target_ids.intersection(base_ids):
                affected_ids.add(str(item_id))
                rollback_source_ids.update(base_ids)

        if affected_ids and not dry_run:
            now = datetime.now().astimezone().isoformat()
            store._db.executemany(
                "UPDATE memory_items SET status='superseded', updated_at=? WHERE id=?",
                [(now, item_id) for item_id in sorted(affected_ids)],
            )
        restored_ids = _restore_replacements_for_undo(
            store,
            affected_ids,
            dry_run=dry_run,
        )
        if not dry_run:
            store._db.commit()
    return {
        "affected_ids": sorted(affected_ids),
        "restored_ids": sorted(restored_ids),
        "rollback_source_ids": sorted(rollback_source_ids),
    }


def _restore_replacements_for_undo(
    store: MemoryStore2,
    affected_ids: set[str],
    *,
    dry_run: bool = False,
) -> set[str]:
    if not affected_ids:
        return set()
    sorted_affected = sorted(affected_ids)
    placeholders = ",".join("?" for _ in sorted_affected)
    rows = store._db.execute(
        f"""
        SELECT DISTINCT old_item_id
        FROM memory_replacements
        WHERE new_item_id IN ({placeholders})
        """,
        tuple(sorted_affected),
    ).fetchall()
    old_ids = {str(row[0]) for row in rows if str(row[0]).strip()}
    restored: set[str] = set()
    now = datetime.now().astimezone().isoformat()
    for old_id in sorted(old_ids):
        active_replacement = store._db.execute(
            """
            SELECT 1
            FROM memory_replacements r
            JOIN memory_items m ON m.id = r.new_item_id
            WHERE r.old_item_id = ?
              AND r.new_item_id NOT IN ({})
              AND m.status = 'active'
            LIMIT 1
            """.format(placeholders),
            tuple([old_id, *sorted_affected]),
        ).fetchone()
        if active_replacement is not None:
            continue
        if dry_run:
            old_row = store._db.execute(
                "SELECT 1 FROM memory_items WHERE id=? AND status='superseded'",
                (old_id,),
            ).fetchone()
            if old_row is not None:
                restored.add(old_id)
            continue
        cur = store._db.execute(
            "UPDATE memory_items SET status='active', updated_at=? WHERE id=? AND status='superseded'",
            (now, old_id),
        )
        if cur.rowcount:
            restored.add(old_id)
    return restored


class _AdminMixin:
    """提供记忆管理、批量操作与撤销能力。"""

    def reinforce_items_batch(self, ids: list[str]) -> None:
        if self._memorizer is not None:
            self._memorizer.reinforce_items_batch(ids)

    def keyword_match_procedures(
        self,
        action_tokens: list[str],
    ) -> list[dict[str, object]]:
        store = self._v2_store
        return (
            store.keyword_match_procedures(action_tokens) if store is not None else []
        )
    def list_events_by_time_range(
        self,
        time_start: datetime,
        time_end: datetime,
        *,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        store = self._v2_store
        if store is None:
            return []
        return store.list_events_by_time_range(time_start, time_end, limit=limit)

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
        store = self._require_v2_store()
        return store.list_items_for_admin(
            q=q,
            memory_type=memory_type,
            memory_domain=memory_domain,
            status=status,
            source_ref=source_ref,
            role_id=role_id,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            has_embedding=has_embedding,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def get_item_for_admin(
        self,
        item_id: str,
        *,
        include_embedding: bool = False,
    ) -> dict[str, object] | None:
        return self._require_v2_store().get_item_for_admin(
            item_id,
            include_embedding=include_embedding,
        )

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
        return self._require_v2_store().update_item_for_admin(
            item_id,
            status=status,
            extra_json=extra_json,
            source_ref=source_ref,
            happened_at=happened_at,
            emotional_weight=emotional_weight,
        )

    def delete_item(self, item_id: str) -> bool:
        return self._require_v2_store().delete_item(item_id)

    def delete_items_batch(self, ids: list[str]) -> int:
        return self._require_v2_store().delete_items_batch(ids)

    def undo_by_message_sources(
        self,
        message_ids: list[str],
        *,
        dry_run: bool = False,
    ) -> dict[str, object]:
        return _undo_store_by_message_sources(
            self._require_v2_store(),
            message_ids,
            dry_run=dry_run,
        )

    def find_similar_items_for_admin(
        self,
        item_id: str,
        *,
        top_k: int = 8,
        memory_type: str = "",
        score_threshold: float = 0.0,
        include_superseded: bool = False,
    ) -> list[dict[str, object]]:
        return self._require_v2_store().find_similar_items_for_admin(
            item_id,
            top_k=top_k,
            memory_type=memory_type,
            score_threshold=score_threshold,
            include_superseded=include_superseded,
        )
