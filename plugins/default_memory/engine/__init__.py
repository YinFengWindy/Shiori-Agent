"""默认记忆引擎的稳定公共入口。"""

import logging

from .admin import (
    _restore_replacements_for_undo,
    _source_ref_message_ids,
    _undo_store_by_message_sources,
)
from .lifecycle import DefaultMemoryEngine, _build_entry_source_ref
from .mutation import (
    _coerce_emotional_weight,
    _coerce_memory_type,
    _dedupe_ids,
    _dict_items,
    _item_matches_forget_scope,
    _split_write_result,
)
from .policy import _NormalizedIngestContent, _keep_count
from .prompts import (
    _build_long_term_prompt,
    _default_memory_tool_profile,
    _explicit_hypothesis_prompt,
)
from .query import (
    _ChatCall,
    _HYPOTHESIS_MAX_TOKENS,
    _HYPOTHESIS_TIMEOUT_S,
    _VECTOR_SCORE_THRESHOLD,
    _VECTOR_TOP_K,
)

logger = logging.getLogger("plugins.default_memory.engine")
