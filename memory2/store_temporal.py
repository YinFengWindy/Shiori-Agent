"""Memory v2 时间范围与关键词检索。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import cast

from memory2.store_common import (
    _MemoryHit,
    _TIME_FILTER_KEYWORD_CANDIDATE_LIMIT,
    _coerce_float,
    _cosine_similarity,
    _is_memory_time_in_range,
    _json_object,
    _parse_memory_time,
    _role_json_filter,
    _time_prefilter_clauses,
)

class _StoreTemporalMixin:
    def list_events_by_time_range(
        self,
        time_start: datetime,
        time_end: datetime,
        limit: int = 200,
        *,
        memory_domains: list[str] | None = None,
        role_id: str | None = None,
        scope_channel: str | None = None,
        scope_chat_id: str | None = None,
        require_scope_match: bool = False,
    ) -> list[dict[str, object]]:
        time_clauses, time_params = _time_prefilter_clauses(
            "happened_at", time_start, time_end
        )
        where_parts = ["memory_type='event'", "status='active'"]
        params: list[object] = []
        if memory_domains:
            placeholders = ",".join("?" for _ in memory_domains)
            where_parts.append(
                "COALESCE(TRIM(json_extract(extra_json, '$.memory_domain')), '') "
                f"IN ({placeholders})"
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
        where_parts.extend(time_clauses)
        params.extend(time_params)
        rows = cast(list[tuple[object, ...]], self._db.execute(
            "SELECT id, memory_type, summary, source_ref, happened_at "
            "FROM memory_items "
            f"WHERE {' AND '.join(where_parts)}",
            tuple(params),
        ).fetchall())

        hits: list[tuple[datetime, dict[str, object]]] = []
        for row_id, memory_type, summary, source_ref, happened_at in rows:
            parsed_time = _parse_memory_time(happened_at)
            if parsed_time is None:
                continue
            if parsed_time < time_start or parsed_time >= time_end:
                continue
            hits.append(
                (
                    parsed_time,
                    {
                        "id": row_id,
                        "memory_type": str(memory_type),
                        "summary": str(summary),
                        "source_ref": str(source_ref) if source_ref else "",
                        "happened_at": str(happened_at) if happened_at else "",
                        "score": 1.0,
                    },
                )
            )

        max_items = max(1, min(limit, 200))
        hits.sort(key=lambda item: item[0], reverse=True)
        selected = hits[:max_items]
        selected.sort(key=lambda item: item[0])
        return [item for _, item in selected]

    def find_similar_recent_events(
        self,
        embedding: list[float],
        *,
        days_back: int = 7,
        threshold: float = 0.92,
        top_k: int = 3,
    ) -> list[str]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, int(days_back)))
        ).isoformat()
        rows = self._db.execute(
            "SELECT id, embedding FROM memory_items "
            "WHERE memory_type='event' AND status='active' "
            "AND embedding IS NOT NULL AND created_at >= ?",
            (cutoff,),
        ).fetchall()
        scored: list[tuple[str, float]] = []
        for row_id, emb_json in rows:
            if not emb_json:
                continue
            score = _cosine_similarity(embedding, json.loads(emb_json))
            if score >= float(threshold):
                scored.append((row_id, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [row_id for row_id, _score in scored[: max(1, int(top_k))]]

    def delete_by_source_ref(self, source_ref: str) -> int:
        """删除指定 source_ref 的所有条目，返回删除行数。"""
        rowids = [
            r[0]
            for r in self._db.execute(
                "SELECT rowid FROM memory_items WHERE source_ref=?", (source_ref,)
            ).fetchall()
        ]
        cur = self._db.execute(
            "DELETE FROM memory_items WHERE source_ref=?", (source_ref,)
        )
        self._vec_delete(rowids)
        self._db.commit()
        return cur.rowcount

    def has_item_by_source_ref(
        self,
        source_ref: str,
        memory_type: str | None = None,
    ) -> bool:
        """检查是否已存在指定 source_ref 的条目。"""
        if memory_type:
            row = self._db.execute(
                "SELECT 1 FROM memory_items WHERE source_ref=? AND memory_type=? LIMIT 1",
                (source_ref, memory_type),
            ).fetchone()
        else:
            row = self._db.execute(
                "SELECT 1 FROM memory_items WHERE source_ref=? LIMIT 1",
                (source_ref,),
            ).fetchone()
        return row is not None

    def keyword_match_procedures(self, action_tokens: list[str]) -> list[dict[str, object]]:
        """对 trigger_tags 做纯关键字匹配，无需向量检索。

        action_tokens 是从工具调用中提取的 token 列表，例如：
          ["shell", "pacman"]  / ["web_search"] / ["read_file", "yt-dlp-downloader"]

        只返回 scope=tool_triggered 且命中的 procedure 条目。
        """
        if not action_tokens:
            return []

        token_set = {t.lower() for t in action_tokens if t}
        action_text = " ".join(action_tokens).lower()

        rows = self._db.execute(
            "SELECT id, summary, extra_json FROM memory_items "
            "WHERE memory_type='procedure' AND status='active' AND extra_json IS NOT NULL"
        ).fetchall()

        matched: list[dict] = []
        for row_id, summary, extra_json_str in rows:
            try:
                extra = json.loads(extra_json_str) if extra_json_str else {}
            except Exception:
                continue
            tags = extra.get("trigger_tags") or {}
            if tags.get("scope") != "tool_triggered":
                continue

            # 过滤掉太短的 keyword（长度 < 3），避免 "i"、"-c" 之类造成误匹配
            keywords = [k for k in (tags.get("keywords") or []) if k and len(k) >= 3]

            if keywords:
                # 有 keyword 时：必须命中至少一个 keyword 才算匹配
                # keyword 是精确区分上下文的标志（如 "pacman"、"bilibili"），
                # 仅靠 tool name 不足以触发（避免 shell/read_file 过度泛化）
                hit = any(kw.lower() in action_text for kw in keywords)
            else:
                # 无 keyword：tool/skill 名精确匹配
                # tools 超过 4 个说明是泛规范（LLM 把全量工具都填进去了），降级为 global 跳过
                proc_tools = tags.get("tools") or []
                proc_skills = tags.get("skills") or []
                if len(proc_tools) > 4:
                    continue
                tag_token_set = {t.lower() for t in proc_tools}
                tag_token_set |= {s.lower() for s in proc_skills}
                hit = bool(token_set & tag_token_set)

            if hit:
                matched.append(
                    {
                        "id": row_id,
                        "memory_type": "procedure",
                        "summary": summary,
                        "extra_json": extra,
                        "intercept": bool(tags.get("intercept", False)),
                        "score": 1.0,
                    }
                )

        return matched

    def keyword_search_summary(
        self,
        terms: list[str],
        memory_types: list[str] | None = None,
        memory_domains: list[str] | None = None,
        role_id: str | None = None,
        limit: int = 20,
        time_start: datetime | None = None,
        time_end: datetime | None = None,
        scope_channel: str | None = None,
        scope_chat_id: str | None = None,
        require_scope_match: bool = False,
    ) -> list[dict[str, object]]:
        """对 summary 字段做 OR-LIKE 关键字检索，按命中词数降序排列。

        每条结果携带 keyword_score（命中词数 / 总词数），供 RRF 融合使用。
        """
        terms = [t for t in terms if t and len(t) >= 2]
        if not terms:
            return []

        type_filter = ""
        type_params: list[str] = []
        if memory_types:
            placeholders = ",".join("?" for _ in memory_types)
            type_filter = f" AND memory_type IN ({placeholders})"
            type_params = list(memory_types)

        domain_filter = ""
        domain_params: list[str] = []
        if memory_domains:
            placeholders = ",".join("?" for _ in memory_domains)
            domain_filter = (
                " AND COALESCE(TRIM(json_extract(extra_json, '$.memory_domain')), '') "
                f"IN ({placeholders})"
            )
            domain_params = [domain.strip() for domain in memory_domains]

        role_filter = ""
        role_params: list[str] = []
        if role_id:
            role_filter = f" AND {_role_json_filter()}"
            role_params = [role_id.strip()]

        scope_filter = ""
        scope_params: list[str] = []
        if require_scope_match:
            scope_filter = (
                " AND COALESCE(TRIM(json_extract(extra_json, '$.scope_channel')), '') = ?"
                " AND COALESCE(TRIM(json_extract(extra_json, '$.scope_chat_id')), '') = ?"
            )
            scope_params = [(scope_channel or "").strip(), (scope_chat_id or "").strip()]

        or_conditions = " OR ".join("summary LIKE ?" for _ in terms)
        score_expr = " + ".join(
            f"(CASE WHEN summary LIKE ? THEN 1 ELSE 0 END)" for _ in terms
        )
        like_vals = [f"%{t}%" for t in terms]

        has_time_filter = time_start is not None or time_end is not None
        time_filter = ""
        time_params: list[object] = []
        if has_time_filter:
            time_clauses, time_params = _time_prefilter_clauses(
                "happened_at", time_start, time_end
            )
            time_filter = " AND " + " AND ".join(time_clauses)
        batch_size = (
            max(limit, _TIME_FILTER_KEYWORD_CANDIDATE_LIMIT)
            if has_time_filter
            else limit
        )
        sql = (
            f"SELECT id, memory_type, summary, extra_json, source_ref, happened_at, created_at, "
            f"reinforcement, ({score_expr}) AS kw_score "
            f"FROM memory_items "
            f"WHERE status='active' AND ({or_conditions}){type_filter}{domain_filter}{role_filter}{scope_filter}{time_filter} "
            f"ORDER BY kw_score DESC, reinforcement DESC, id ASC "
            f"LIMIT ? OFFSET ?"
        )
        results: list[_MemoryHit] = []
        offset = 0
        while True:
            params: Sequence[object] = tuple(
                like_vals
                + like_vals
                + type_params
                + domain_params
                + role_params
                + scope_params
                + time_params
                + [batch_size, offset]
            )
            rows = cast(
                list[tuple[object, ...]],
                self._db.execute(sql, params).fetchall(),
            )
            if not rows:
                break
            for row in rows:
                (
                    row_id,
                    mtype,
                    summary,
                    extra_json,
                    source_ref,
                    happened_at,
                    created_at,
                    _reinforcement,
                    kw_score,
                ) = row
                if has_time_filter and not _is_memory_time_in_range(
                    happened_at, time_start, time_end
                ):
                    continue
                extra = _json_object(extra_json)
                results.append({
                    "id": str(row_id),
                    "memory_type": str(mtype),
                    "memory_domain": str(extra.get("memory_domain", "") or ""),
                    "summary": str(summary),
                    "source_ref": str(source_ref) if source_ref else "",
                    "happened_at": str(happened_at or created_at or ""),
                    "keyword_score": _coerce_float(kw_score) / len(terms),
                })
                if len(results) >= limit:
                    return results
            if not has_time_filter or len(rows) < batch_size:
                break
            offset += batch_size
        return results
