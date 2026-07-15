"""Memory v2 SQLite 存储 facade。

`MemoryStore2` 与历史 helper 导入均保留在本模块，具体职责由 store_* 模块实现。
"""

from __future__ import annotations

from memory2.store_common import (
    SCHEMA,
    VEC_DIM,
    _EmbeddingRow,
    _LOCAL_TZ,
    _MemoryHit,
    _TIME_FILTER_KEYWORD_CANDIDATE_LIMIT,
    _TIME_FILTER_MARGIN,
    _coerce_emotional_weight,
    _coerce_float,
    _coerce_int,
    _content_hash,
    _cosine_similarity,
    _domain_json_filter,
    _emb_to_blob,
    _hotness_score,
    _is_memory_time_in_range,
    _json_embedding,
    _json_object,
    _l2dist_to_cosine,
    _local_naive_iso,
    _normalize_emb,
    _now_iso,
    _parse_memory_time,
    _result_score,
    _role_json_filter,
    _time_prefilter_clauses,
)
from memory2.store_admin import _StoreAdminMixin
from memory2.store_connection import _SQLITE_VEC_AVAILABLE, _StoreConnection
from memory2.store_temporal import _StoreTemporalMixin
from memory2.store_vector import _StoreVectorMixin
from memory2.store_write import _StoreWriteMixin


class MemoryStore2(
    _StoreWriteMixin,
    _StoreAdminMixin,
    _StoreVectorMixin,
    _StoreTemporalMixin,
    _StoreConnection,
):
    """Memory v2 的稳定存储入口，组合写入、向量和时间检索能力。"""
