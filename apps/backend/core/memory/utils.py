from __future__ import annotations

from core.memory.engine import EvidenceRef, MemoryQuery, MemoryScope


def evidence_from_source_ref(source_ref: str) -> list[EvidenceRef]:
    value = (source_ref or "").strip()
    if not value:
        return []
    return [EvidenceRef(refs=[value], source_ref=value)]


def source_ref_from_evidence(
    evidence: list[EvidenceRef],
    *,
    fallback: str = "",
) -> str:
    for item in evidence:
        if item.source_ref.strip():
            return item.source_ref.strip()
        if item.refs:
            return item.refs[0]
    return fallback


def resolve_memory_scope(scope: MemoryScope) -> MemoryScope:
    if scope.role_id:
        return scope
    raise ValueError("role_id required for memory scope")


def should_require_scope_match(request: MemoryQuery, scope: MemoryScope) -> bool:
    if request.intent in {"answer", "interest"}:
        return True
    return bool(request.filters.hints.get("require_scope_match", False))
