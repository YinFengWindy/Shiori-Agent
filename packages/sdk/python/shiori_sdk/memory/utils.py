from __future__ import annotations

from shiori_sdk.memory.engine import EvidenceRef, MemoryQuery, MemoryScope


def evidence_from_source_ref(source_ref: str) -> list[EvidenceRef]:
    """Turns a persisted source reference into portable evidence."""
    value = (source_ref or "").strip()
    if not value:
        return []
    return [EvidenceRef(refs=[value], source_ref=value)]


def resolve_memory_scope(scope: MemoryScope) -> MemoryScope:
    """Rejects memory access without an explicit role scope."""
    if scope.role_id:
        return scope
    raise ValueError("role_id required for memory scope")


def should_require_scope_match(request: MemoryQuery, scope: MemoryScope) -> bool:
    """Applies the query intent's minimum conversation-scope requirement."""
    if request.intent in {"answer", "interest"}:
        return True
    return bool(request.filters.hints.get("require_scope_match", False))
