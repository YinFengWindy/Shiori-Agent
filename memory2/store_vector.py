"""Memory v2 向量候选检索与评分。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
import numpy as np
import logging

logger = logging.getLogger(__name__)

from memory2.store_common import (
    _EmbeddingRow,
    _MemoryHit,
    _coerce_emotional_weight,
    _coerce_float,
    _coerce_int,
    _emb_to_blob,
    _hotness_score,
    _is_memory_time_in_range,
    _json_embedding,
    _json_object,
    _l2dist_to_cosine,
    _result_score,
    _role_json_filter,
    _time_prefilter_clauses,
)

class _StoreVectorMixin:
    def get_all_with_embedding(self, include_superseded: bool = False) -> list[_EmbeddingRow]:
        """返回 [(id, memory_type, summary, embedding_list, extra_json_dict, happened_at, source_ref)]
        extra_json_dict 中注入 _reinforcement / _updated_at / _emotional_weight
        （_ 前缀，不污染用户字段）。
        """
        where = "" if include_superseded else "AND status='active'"
        rows = cast(list[tuple[object, ...]], self._db.execute(
            "SELECT id, memory_type, summary, embedding, extra_json, happened_at, "
            "reinforcement, updated_at, source_ref, emotional_weight "
            f"FROM memory_items WHERE embedding IS NOT NULL {where}"
        ).fetchall())
        result: list[_EmbeddingRow] = []
        for row in rows:
            (
                row_id,
                mtype,
                summary,
                emb_json,
                extra_json,
                happened_at,
                reinforcement,
                updated_at,
                source_ref,
                emotional_weight,
            ) = row
            emb = _json_embedding(emb_json)
            extra = _json_object(extra_json)
            extra["_reinforcement"] = _coerce_int(reinforcement, 1)
            extra["_updated_at"] = str(updated_at) if updated_at else ""
            extra["_emotional_weight"] = _coerce_emotional_weight(emotional_weight)
            result.append(
                (
                    str(row_id),
                    str(mtype),
                    str(summary),
                    emb,
                    extra,
                    str(happened_at) if happened_at else None,
                    str(source_ref) if source_ref else None,
                )
            )
        return result

    def _get_embedding_rows_by_time_filter(
        self,
        *,
        memory_types: list[str] | None,
        memory_domains: list[str] | None,
        include_superseded: bool,
        role_id: str | None,
        scope_channel: str | None,
        scope_chat_id: str | None,
        require_scope_match: bool,
        time_start: datetime | None,
        time_end: datetime | None,
    ) -> list[_EmbeddingRow]:
        where_parts = ["embedding IS NOT NULL"]
        params: list[object] = []
        if not include_superseded:
            where_parts.append("status='active'")
        if memory_types:
            placeholders = ",".join("?" for _ in memory_types)
            where_parts.append(f"memory_type IN ({placeholders})")
            params.extend(memory_types)
        if memory_domains:
            placeholders = ",".join("?" for _ in memory_domains)
            where_parts.append(
                f"COALESCE(TRIM(json_extract(extra_json, '$.memory_domain')), '') IN ({placeholders})"
            )
            params.extend([domain.strip() for domain in memory_domains])
        if role_id:
            where_parts.append(_role_json_filter())
            params.append(role_id.strip())
        if require_scope_match:
            where_parts.append(
                "COALESCE(TRIM(json_extract(extra_json, '$.scope_channel')), '') = ?"
            )
            where_parts.append(
                "COALESCE(TRIM(json_extract(extra_json, '$.scope_chat_id')), '') = ?"
            )
            params.extend([(scope_channel or "").strip(), (scope_chat_id or "").strip()])
        time_clauses, time_params = _time_prefilter_clauses(
            "happened_at", time_start, time_end
        )
        where_parts.extend(time_clauses)
        params.extend(time_params)

        rows = cast(list[tuple[object, ...]], self._db.execute(
            "SELECT id, memory_type, summary, embedding, extra_json, happened_at, "
            "reinforcement, updated_at, source_ref, emotional_weight "
            f"FROM memory_items WHERE {' AND '.join(where_parts)}",
            tuple(params),
        ).fetchall())
        result: list[_EmbeddingRow] = []
        for row in rows:
            (
                row_id,
                mtype,
                summary,
                emb_json,
                extra_json,
                happened_at,
                reinforcement,
                updated_at,
                source_ref,
                emotional_weight,
            ) = row
            if not _is_memory_time_in_range(happened_at, time_start, time_end):
                continue
            emb = _json_embedding(emb_json)
            extra = _json_object(extra_json)
            extra["_reinforcement"] = _coerce_int(reinforcement, 1)
            extra["_updated_at"] = str(updated_at) if updated_at else ""
            extra["_emotional_weight"] = _coerce_emotional_weight(emotional_weight)
            result.append(
                (
                    str(row_id),
                    str(mtype),
                    str(summary),
                    emb,
                    extra,
                    str(happened_at) if happened_at else None,
                    str(source_ref) if source_ref else None,
                )
            )
        return result

    def vector_search(
        self,
        query_vec: list[float],
        top_k: int = 8,
        memory_types: list[str] | None = None,
        memory_domains: list[str] | None = None,
        score_threshold: float = 0.0,
        include_superseded: bool = False,
        role_id: str | None = None,
        scope_channel: str | None = None,
        scope_chat_id: str | None = None,
        require_scope_match: bool = False,
        hotness_alpha: float = 0.0,
        hotness_half_life_days: float = 14.0,
        time_start: datetime | None = None,
        time_end: datetime | None = None,
    ) -> list[dict[str, object]]:
        """cosine similarity 检索，返回 top-k 结果。
        hotness_alpha > 0 时启用热度融合：final = (1-alpha)*semantic + alpha*hotness。
        """
        if time_start is not None or time_end is not None:
            return self._vector_search_fullscan(
                query_vec,
                top_k=top_k,
                memory_types=memory_types,
                memory_domains=memory_domains,
                score_threshold=score_threshold,
                include_superseded=include_superseded,
                role_id=role_id,
                scope_channel=scope_channel,
                scope_chat_id=scope_chat_id,
                require_scope_match=require_scope_match,
                hotness_alpha=hotness_alpha,
                hotness_half_life_days=hotness_half_life_days,
                time_start=time_start,
                time_end=time_end,
            )
        if self._vec_enabled:
            return self._vector_search_vec(
                query_vec,
                top_k=top_k,
                memory_types=memory_types,
                score_threshold=score_threshold,
                include_superseded=include_superseded,
                role_id=role_id,
                scope_channel=scope_channel,
                scope_chat_id=scope_chat_id,
                require_scope_match=require_scope_match,
                hotness_alpha=hotness_alpha,
                hotness_half_life_days=hotness_half_life_days,
            )
        if not self._vec_fallback_logged:
            reason = self._vec_init_error or "sqlite-vec 未启用"
            logger.warning("vector_search 已降级为全表扫描：%s", reason)
            self._vec_fallback_logged = True
        return self._vector_search_fullscan(
            query_vec,
            top_k=top_k,
            memory_types=memory_types,
            memory_domains=memory_domains,
            score_threshold=score_threshold,
            include_superseded=include_superseded,
            role_id=role_id,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            require_scope_match=require_scope_match,
            hotness_alpha=hotness_alpha,
            hotness_half_life_days=hotness_half_life_days,
        )

    def vector_search_batch(
        self,
        query_vecs: list[list[float]],
        top_k: int = 8,
        memory_types: list[str] | None = None,
        memory_domains: list[str] | None = None,
        score_threshold: float = 0.0,
        include_superseded: bool = False,
        role_id: str | None = None,
        scope_channel: str | None = None,
        scope_chat_id: str | None = None,
        require_scope_match: bool = False,
        hotness_alpha: float = 0.0,
        hotness_half_life_days: float = 14.0,
        time_start: datetime | None = None,
        time_end: datetime | None = None,
    ) -> list[list[dict[str, object]]]:
        if not query_vecs:
            return []
        if time_start is None and time_end is None:
            return [
                self.vector_search(
                    query_vec,
                    top_k=top_k,
                    memory_types=memory_types,
                    memory_domains=memory_domains,
                    score_threshold=score_threshold,
                    include_superseded=include_superseded,
                    role_id=role_id,
                    scope_channel=scope_channel,
                    scope_chat_id=scope_chat_id,
                    require_scope_match=require_scope_match,
                    hotness_alpha=hotness_alpha,
                    hotness_half_life_days=hotness_half_life_days,
                )
                for query_vec in query_vecs
            ]

        rows = self._get_embedding_rows_by_time_filter(
            memory_types=memory_types,
            memory_domains=memory_domains,
            include_superseded=include_superseded,
            role_id=role_id,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            require_scope_match=require_scope_match,
            time_start=time_start,
            time_end=time_end,
        )
        return [
            self._score_embedding_rows(
                query_vec,
                rows,
                top_k=top_k,
                score_threshold=score_threshold,
                hotness_alpha=hotness_alpha,
                hotness_half_life_days=hotness_half_life_days,
            )
            for query_vec in query_vecs
        ]

    def _vector_search_vec(
        self,
        query_vec: list[float],
        top_k: int = 8,
        memory_types: list[str] | None = None,
        memory_domains: list[str] | None = None,
        score_threshold: float = 0.0,
        include_superseded: bool = False,
        role_id: str | None = None,
        scope_channel: str | None = None,
        scope_chat_id: str | None = None,
        require_scope_match: bool = False,
        hotness_alpha: float = 0.0,
        hotness_half_life_days: float = 14.0,
    ) -> list[_MemoryHit]:
        """sqlite-vec KNN 检索路径。维度不符时自动回退全表扫描。"""
        if len(query_vec) != self._vec_dim:
            logger.debug(
                "query dim %d ≠ vec_dim %d，回退全表扫描", len(query_vec), self._vec_dim
            )
            return self._vector_search_fullscan(
                query_vec,
                top_k=top_k,
                memory_types=memory_types,
                memory_domains=memory_domains,
                score_threshold=score_threshold,
                include_superseded=include_superseded,
                role_id=role_id,
                scope_channel=scope_channel,
                scope_chat_id=scope_chat_id,
                require_scope_match=require_scope_match,
                hotness_alpha=hotness_alpha,
                hotness_half_life_days=hotness_half_life_days,
            )
        blob = _emb_to_blob(query_vec)

        # KNN 多取一些候选，以补偿 score_threshold 截断的损耗
        fetch_k = max(top_k * 2, 20)

        params: list[object] = [blob, fetch_k]

        status_filter = "" if include_superseded else "AND m.status = 'active'"

        # memory_type 推入 SQL 过滤，避免 Python 二次扫描
        if memory_types:
            placeholders = ",".join("?" * len(memory_types))
            type_filter = f"AND m.memory_type IN ({placeholders})"
            params.extend(memory_types)
        else:
            type_filter = ""

        if memory_domains:
            placeholders = ",".join("?" for _ in memory_domains)
            domain_filter = (
                "AND COALESCE(TRIM(json_extract(m.extra_json, '$.memory_domain')), '') "
                f"IN ({placeholders})"
            )
            params.extend([domain.strip() for domain in memory_domains])
        else:
            domain_filter = ""

        if role_id:
            role_filter = f"AND {_role_json_filter('m.extra_json')}"
            params.append(role_id.strip())
        else:
            role_filter = ""

        # scope 推入 SQL，用 json_extract 读取 extra_json 字段
        if require_scope_match:
            s_channel = (scope_channel or "").strip()
            s_chat = (scope_chat_id or "").strip()
            scope_filter = (
                "AND COALESCE(TRIM(json_extract(m.extra_json, '$.scope_channel')), '') = ?"
                " AND COALESCE(TRIM(json_extract(m.extra_json, '$.scope_chat_id')), '') = ?"
            )
            params.extend([s_channel, s_chat])
        else:
            scope_filter = ""

        sql = f"""
            SELECT m.id, m.memory_type, m.summary, m.extra_json, m.happened_at,
                   m.reinforcement, m.updated_at, m.source_ref, m.emotional_weight,
                   v.distance
            FROM (
                SELECT rowid, distance
                FROM vec_items
                WHERE embedding MATCH ?
                  AND k = ?
            ) v
            JOIN memory_items m ON m.rowid = v.rowid
            WHERE 1=1 {status_filter} {type_filter} {domain_filter} {role_filter} {scope_filter}
            ORDER BY v.distance ASC
        """
        rows = cast(list[tuple[object, ...]], self._db.execute(sql, tuple(params)).fetchall())

        now = datetime.now(timezone.utc)
        scored: list[_MemoryHit] = []
        for row in rows:
            (
                row_id,
                mtype,
                summary,
                extra_json,
                happened_at,
                reinforcement,
                updated_at_raw,
                source_ref,
                emotional_weight,
                distance,
            ) = row
            # L2 distance on unit sphere → cosine similarity
            similarity = _l2dist_to_cosine(_coerce_float(distance))
            if similarity < score_threshold:
                continue

            extra = _json_object(extra_json)
            reinforcement_int = _coerce_int(reinforcement, 1)
            updated_at_str = str(updated_at_raw) if updated_at_raw else ""
            emotional_weight_int = _coerce_emotional_weight(emotional_weight)
            extra["_reinforcement"] = reinforcement_int
            extra["_updated_at"] = updated_at_str
            extra["_emotional_weight"] = emotional_weight_int

            hotness = 0.0
            if hotness_alpha > 0 and updated_at_str:
                try:
                    updated_at = datetime.fromisoformat(updated_at_str)
                    hotness = _hotness_score(
                        reinforcement_int,
                        updated_at,
                        now,
                        hotness_half_life_days,
                        emotional_weight=emotional_weight_int,
                    )
                except (ValueError, TypeError):
                    pass

            final = (1.0 - hotness_alpha) * similarity + hotness_alpha * hotness
            scored.append(
                {
                    "id": str(row_id),
                    "memory_type": str(mtype),
                    "memory_domain": str(extra.get("memory_domain", "") or ""),
                    "summary": str(summary),
                    "extra_json": extra,
                    "happened_at": str(happened_at) if happened_at else "",
                    "source_ref": str(source_ref) if source_ref else "",
                    "score": round(final, 4),
                    "_score_debug": {
                        "semantic": round(similarity, 4),
                        "hotness": round(hotness, 4),
                        "final": round(final, 4),
                    },
                }
            )

        scored.sort(key=_result_score, reverse=True)
        return scored[:top_k]
    def _vector_search_fullscan(
        self,
        query_vec: list[float],
        top_k: int = 8,
        memory_types: list[str] | None = None,
        memory_domains: list[str] | None = None,
        score_threshold: float = 0.0,
        include_superseded: bool = False,
        role_id: str | None = None,
        scope_channel: str | None = None,
        scope_chat_id: str | None = None,
        require_scope_match: bool = False,
        hotness_alpha: float = 0.0,
        hotness_half_life_days: float = 14.0,
        time_start: datetime | None = None,
        time_end: datetime | None = None,
    ) -> list[_MemoryHit]:
        """全表扫描回退路径（sqlite-vec 不可用时使用）。"""
        has_time_filter = time_start is not None or time_end is not None
        if has_time_filter:
            rows = self._get_embedding_rows_by_time_filter(
                memory_types=memory_types,
                memory_domains=memory_domains,
                include_superseded=include_superseded,
                role_id=role_id,
                scope_channel=scope_channel,
                scope_chat_id=scope_chat_id,
                require_scope_match=require_scope_match,
                time_start=time_start,
                time_end=time_end,
            )
        else:
            rows = self.get_all_with_embedding(include_superseded=include_superseded)
        if not rows:
            return []

        if memory_types and not has_time_filter:
            rows = [r for r in rows if r[1] in memory_types]

        if memory_domains and not has_time_filter:
            clean_domains = {domain.strip() for domain in memory_domains}
            rows = [
                r
                for r in rows
                if str((r[4] or {}).get("memory_domain", "")).strip() in clean_domains
            ]

        if role_id and not has_time_filter:
            clean_role_id = role_id.strip()
            rows = [
                r
                for r in rows
                if str((r[4] or {}).get("role_id", "")).strip() == clean_role_id
            ]

        if require_scope_match and not has_time_filter:
            s_channel = (scope_channel or "").strip()
            s_chat = (scope_chat_id or "").strip()
            rows = [
                r
                for r in rows
                if str((r[4] or {}).get("scope_channel", "")).strip() == s_channel
                and str((r[4] or {}).get("scope_chat_id", "")).strip() == s_chat
            ]

        return self._score_embedding_rows(
            query_vec,
            rows,
            top_k=top_k,
            score_threshold=score_threshold,
            hotness_alpha=hotness_alpha,
            hotness_half_life_days=hotness_half_life_days,
        )

    def _score_embedding_rows(
        self,
        query_vec: list[float],
        rows: list[_EmbeddingRow],
        *,
        top_k: int,
        score_threshold: float,
        hotness_alpha: float,
        hotness_half_life_days: float,
    ) -> list[dict[str, object]]:
        if not rows:
            return []

        q = np.array(query_vec, dtype=np.float32)
        q_norm = float(np.linalg.norm(q)) + 1e-9
        now = datetime.now(timezone.utc)
        scored: list[_MemoryHit] = []
        for row_id, mtype, summary, emb, extra, happened_at, source_ref in rows:
            if emb is None:
                continue
            e = np.array(emb, dtype=np.float32)
            semantic = float(e @ q) / (float(np.linalg.norm(e)) + 1e-9) / q_norm
            if semantic < score_threshold:
                continue

            hotness = 0.0
            if hotness_alpha > 0:
                reinforcement = _coerce_int(extra.get("_reinforcement"), 1)
                updated_at_raw = extra.get("_updated_at")
                updated_at_str = updated_at_raw if isinstance(updated_at_raw, str) else ""
                emotional_weight = _coerce_emotional_weight(
                    extra.get("_emotional_weight", 0)
                )
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str)
                        hotness = _hotness_score(
                            reinforcement,
                            updated_at,
                            now,
                            hotness_half_life_days,
                            emotional_weight=emotional_weight,
                        )
                    except (ValueError, TypeError):
                        pass

            final = (1.0 - hotness_alpha) * semantic + hotness_alpha * hotness

            scored.append(
                {
                    "id": row_id,
                    "memory_type": mtype,
                    "summary": summary,
                    "extra_json": extra,
                    "happened_at": happened_at or "",
                    "source_ref": source_ref or "",
                    "score": round(final, 4),
                    "_score_debug": {
                        "semantic": round(semantic, 4),
                        "hotness": round(hotness, 4),
                        "final": round(final, 4),
                    },
                }
            )

        scored.sort(key=_result_score, reverse=True)
        return scored[:top_k]
