"""Memory v2 存储包共享的 schema、类型与纯转换 helper。"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from datetime import datetime, timedelta, timezone
from typing import cast
from zoneinfo import ZoneInfo

import numpy as np

VEC_DIM = 1024  # 默认维度，MemoryStore2 构造时可覆盖
_LOCAL_TZ = ZoneInfo("Asia/Shanghai")
_MemoryHit = dict[str, object]
_EmbeddingRow = tuple[
    str,
    str,
    str,
    list[float] | None,
    dict[str, object],
    str | None,
    str | None,
]
_TIME_FILTER_MARGIN = timedelta(days=2)
_TIME_FILTER_KEYWORD_CANDIDATE_LIMIT = 1000

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_items (
    id            TEXT PRIMARY KEY,
    memory_type   TEXT NOT NULL,
    summary       TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    embedding     TEXT,
    reinforcement INTEGER NOT NULL DEFAULT 1,
    emotional_weight INTEGER NOT NULL DEFAULT 0,
    extra_json    TEXT,
    source_ref    TEXT,
    happened_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_items_hash
    ON memory_items (content_hash, memory_type);
CREATE TABLE IF NOT EXISTS consolidation_events (
    source_ref  TEXT PRIMARY KEY,
    item_id     TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_replacements (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    old_item_id       TEXT NOT NULL,
    old_memory_type   TEXT NOT NULL,
    old_summary       TEXT NOT NULL,
    old_source_ref    TEXT,
    old_happened_at   TEXT,
    old_extra_json    TEXT,
    new_item_id       TEXT NOT NULL,
    new_memory_type   TEXT NOT NULL,
    new_summary       TEXT NOT NULL,
    new_source_ref    TEXT,
    new_happened_at   TEXT,
    new_extra_json    TEXT,
    relation_type     TEXT NOT NULL DEFAULT 'supersede',
    source_ref        TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_memory_replacements_old_item
    ON memory_replacements (old_item_id, created_at);
CREATE INDEX IF NOT EXISTS ix_memory_replacements_new_item
    ON memory_replacements (new_item_id, created_at);
"""

# VEC_SCHEMA 在 MemoryStore2.__init__ 中按 vec_dim 动态生成


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(summary: str, memory_type: str) -> str:
    text = re.sub(r"\s+", " ", summary.lower().strip()) + memory_type
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _coerce_emotional_weight(value: object) -> int:
    if value is None or value == "":
        return 0
    if not isinstance(value, str | int | float):
        return 0
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return 0


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str | float):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _coerce_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _json_object(raw: object) -> dict[str, object]:
    if not raw:
        return {}
    data = json.loads(str(raw))
    return cast(dict[str, object], data) if isinstance(data, dict) else {}


def _json_embedding(raw: object) -> list[float] | None:
    if not raw:
        return None
    return cast(list[float], json.loads(str(raw)))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    a_norm = float(np.linalg.norm(va)) + 1e-9
    b_norm = float(np.linalg.norm(vb)) + 1e-9
    return float(va @ vb) / a_norm / b_norm


def _hotness_score(
    reinforcement: int,
    updated_at: datetime,
    now: datetime | None = None,
    half_life_days: float = 14.0,
    emotional_weight: int = 0,
) -> float:
    """计算热度分：频度 * 时间衰减，结果在 (0, 1) 区间。"""
    if now is None:
        now = datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    effective_half_life = max(
        half_life_days * (1.0 + 0.5 * _coerce_emotional_weight(emotional_weight) / 10.0),
        0.1,
    )
    freq    = 1.0 / (1.0 + math.exp(-math.log1p(max(0, reinforcement))))
    age_d   = max((now - updated_at).total_seconds() / 86400.0, 0.0)
    recency = math.exp(-math.log(2) / effective_half_life * age_d)
    return freq * recency


def _normalize_emb(emb: list[float]) -> list[float]:
    """L2 归一化，供 vec_items 存储用（L2 KNN on unit vectors ≡ cosine ranking）。"""
    v = np.array(emb, dtype=np.float32)
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return emb
    return (v / n).tolist()


def _emb_to_blob(emb: list[float]) -> bytes:
    """将归一化后的 embedding 打包为 float32 blob。"""
    normed = _normalize_emb(emb)
    return struct.pack(f"{len(normed)}f", *normed)


def _l2dist_to_cosine(distance: float) -> float:
    """将单位球上的 L2 距离转换回 cosine similarity。
    |a-b|² = 2(1 - cos) → cos = 1 - d²/2
    """
    return 1.0 - (distance * distance) / 2.0


def _parse_memory_time(raw: object) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_LOCAL_TZ)
    return dt.astimezone(_LOCAL_TZ)


def _is_memory_time_in_range(
    raw: object,
    time_start: datetime | None,
    time_end: datetime | None,
) -> bool:
    dt = _parse_memory_time(raw)
    if dt is None:
        return False
    if time_start is not None and dt < time_start:
        return False
    if time_end is not None and dt >= time_end:
        return False
    return True


def _result_score(item: dict[str, object]) -> float:
    raw = item.get("score", 0.0)
    return float(raw) if isinstance(raw, int | float) else 0.0


def _local_naive_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        local_dt = dt.replace(tzinfo=_LOCAL_TZ)
    else:
        local_dt = dt.astimezone(_LOCAL_TZ)
    return local_dt.replace(tzinfo=None).isoformat(timespec="seconds")


def _time_prefilter_clauses(
    column: str,
    time_start: datetime | None,
    time_end: datetime | None,
) -> tuple[list[str], list[object]]:
    clauses = [f"{column} IS NOT NULL", f"TRIM({column}) != ''"]
    params: list[object] = []
    if time_start is not None:
        clauses.append(f"{column} >= ?")
        params.append(_local_naive_iso(time_start - _TIME_FILTER_MARGIN))
    if time_end is not None:
        clauses.append(f"{column} < ?")
        params.append(_local_naive_iso(time_end + _TIME_FILTER_MARGIN))
    return clauses, params


def _role_json_filter(column: str = "extra_json") -> str:
    return f"COALESCE(TRIM(json_extract({column}, '$.role_id')), '') = ?"


def _domain_json_filter(column: str = "extra_json") -> str:
    return f"COALESCE(TRIM(json_extract({column}, '$.memory_domain')), '') = ?"
