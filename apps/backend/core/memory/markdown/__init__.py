"""Markdown memory 的稳定 facade。"""

from .consolidation import (
    _EVENT_EXTRACTION_TIMEOUT_S,
    _MarkdownConsolidationWorker,
)
from .contracts import (
    ConsolidateRequest,
    ConsolidateResult,
    MemoryLifecycleBindRequest,
    MemoryProfileApi,
    RefreshRecentTurnsRequest,
    _ConsolidationDraft,
    _ConsolidationFailure,
    _ConsolidationWindow,
)
from .formatting import (
    _ALLOWED_PENDING_TAGS,
    _DATE_PREFIX_RE,
    _NSFW_MEMORY_AFFECTION_RE,
    _NSFW_MEMORY_DEPENDENCY_RE,
    _NSFW_MEMORY_EXPLICIT_RE,
    _NSFW_MEMORY_IMAGE_RE,
    _NSFW_MEMORY_LOVE_RE,
    _NSFW_MEMORY_SHY_RE,
    _abstract_nsfw_memory_content,
    _append_entries_to_journal,
    _build_consolidation_source_ref,
    _build_entry_source_ref,
    _coerce_emotional_weight,
    _coerce_history_text,
    _dedupe_semantic_items,
    _format_consolidation_error,
    _format_conversation_for_consolidation,
    _format_pending_items,
    _is_context_frame_message,
    _is_memory_maintenance_assistant_message,
    _is_nsfw_memory_enabled_session,
    _normalize_history_entries,
    _normalize_memory_content,
    _parse_consolidation_payload,
    _select_consolidation_window,
    _select_recent_history_entries,
    _session_role_runtime_config,
)
from .maintenance import MarkdownMemoryMaintenance
from .recent_context import (
    _RECENT_CONTEXT_TIMEOUT_S,
    _format_conversation_for_recent_context,
    _format_recent_context_messages,
    _message_time,
    _recent_turn_count,
    _render_recent_context,
    _replace_recent_turns_block,
)
from .runtime import (
    MarkdownMemoryRuntime,
    MarkdownMemoryStore,
    build_markdown_memory_runtime,
    resolve_markdown_store,
)

__all__ = [
    "ConsolidateRequest",
    "ConsolidateResult",
    "MarkdownMemoryMaintenance",
    "MarkdownMemoryRuntime",
    "MarkdownMemoryStore",
    "MemoryLifecycleBindRequest",
    "MemoryProfileApi",
    "RefreshRecentTurnsRequest",
    "build_markdown_memory_runtime",
    "resolve_markdown_store",
]
