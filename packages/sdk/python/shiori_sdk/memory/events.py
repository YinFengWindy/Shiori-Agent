from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


def _empty_hit_metadata() -> dict[str, object]:
    return {}


def _empty_str_list() -> list[str]:
    return []


@dataclass(frozen=True)
class RetrievalHitSummary:
    """Compact retrieval evidence carried by lifecycle observations."""

    item_id: str
    memory_type: str
    score: float
    summary: str
    injected: bool
    confidence_label: str = ""
    forced: bool = False
    metadata: dict[str, object] = field(default_factory=_empty_hit_metadata)


@dataclass(frozen=True)
class RetrievalCompleted:
    """Observation emitted after a scoped retrieval finishes."""

    session_key: str
    channel: str
    chat_id: str
    query: str
    orig_query: str | None
    hits: list[RetrievalHitSummary]
    injected_count: int
    route_decision: str | None
    aux_queries: list[str] = field(default_factory=_empty_str_list)
    error: str | None = None
    role_id: str = ""


@dataclass(frozen=True)
class MemoryWritten:
    """Observation of a memory write or supersede operation."""

    session_key: str
    channel: str
    chat_id: str
    action: Literal["write", "supersede"]
    source_ref: str
    memory_type: str | None = None
    item_id: str | None = None
    summary: str | None = None
    superseded_ids: list[str] = field(default_factory=_empty_str_list)
    error: str | None = None
    role_id: str = ""


@dataclass(frozen=True)
class TurnIngested:
    """Committed conversation content queued for post-response memory work."""

    session_key: str
    channel: str
    chat_id: str
    user_message: str
    assistant_response: str
    tool_chain: list[dict[str, object]]
    source_ref: str
    role_id: str = ""


@dataclass(frozen=True)
class ConsolidationCommitted:
    """Persisted Markdown consolidation payload consumed by semantic engines."""

    history_entry_payloads: list[tuple[str, int]]
    source_ref: str
    scope_channel: str
    scope_chat_id: str
    conversation: str
    role_id: str = ""
