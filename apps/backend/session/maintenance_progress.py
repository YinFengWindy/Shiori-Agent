"""Durable, independent memory/consumer versions and model window progress."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import hashlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from conversation.context_scope import ContextView, UserContextThreads


def ownership_key(threads: UserContextThreads | None) -> str:
    """Stable ownership stamp; binding changes invalidate prepared visibility."""
    return (
        json.dumps(sorted(threads.bound_chat_thread_ids), ensure_ascii=False)
        if threads is not None
        else ""
    )


def window_key(view: ContextView | None) -> str:
    """User threads share one window; each external thread owns its own."""
    if view is None:
        return "session"
    if view.scope == "user":
        return "user"
    if not view.thread_id:
        raise ValueError("外部窗口必须指定实际会话")
    return "external:" + view.thread_id


def message_prefix_stamp(messages: list[dict]) -> str:
    """Guard every semantic persisted field, including future tool payload fields.

    Exclude only storage bookkeeping, and normalize optional SQL-column defaults
    that disappear on a reload. Metadata, reasoning, proactive flags, native tool
    calls/results and independently stored model-visible content remain included.
    """
    from session.manager.models import message_thread_id

    snapshot = []
    for message in messages:
        row = {
            key: value
            for key, value in message.items()
            if key not in {"session_key", "seq", "thread_id"}
            and value is not None
            and not (
                key
                in {"sender_role", "external_message_id", "delivery_status", "media"}
                and not value
            )
        }
        row["thread_id"] = message_thread_id(message)
        snapshot.append(row)
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class MaintenanceProgress:
    """Frozen legacy cuts plus independent progress, never written by message saves.

    Legacy cuts are frozen for *both* categories before the first memory advance;
    a previously unread external thread therefore keeps its original first view.
    Consumer versions remain behind memory_version when a downstream step fails.
    """

    ownership: str = ""
    legacy_cuts: dict[str, int] = field(default_factory=dict)
    windows: dict[str, int] = field(default_factory=dict)
    window_versions: dict[str, int] = field(default_factory=dict)
    compaction_counts: dict[str, int] = field(default_factory=dict)
    summaries: dict[str, str] = field(default_factory=dict)
    summary_source_ids: dict[str, list[str]] = field(default_factory=dict)
    request_owners: dict[str, str] = field(default_factory=dict)
    generation: int = 0
    memory_version: int = 0
    recent_context_version: int = 0
    recent_context_source_ids: list[str] = field(default_factory=list)
    published_version: int = 0
    relationship_version: int = 0
    consumer_error: str = ""
    pending_consumers: dict[str, Any] = field(default_factory=dict)

    def invalidated(self, *, ownership: str | None = None) -> MaintenanceProgress:
        """Return a new generation without mutating the previous state snapshot.

        Identity changes supply the new ownership stamp. Undo, explicit reset and
        clear retain it; their owners separately decide how memory cursors move.
        """
        return MaintenanceProgress(
            ownership=self.ownership if ownership is None else ownership,
            generation=self.generation + 1,
            memory_version=self.memory_version + 1,
        )

    def cursor(self, view: ContextView | None) -> int:
        """Read the effective window cut without changing memory progress."""
        if self.ownership != ownership_key(view.user_threads if view else None):
            return 0
        key = window_key(view)
        return self.windows.get(
            key, self.legacy_cuts.get(view.scope if view else "session", 0)
        )

    def dump(self) -> str:
        """Serialize the owner state independently from ordinary session metadata."""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def load(cls, raw: str) -> MaintenanceProgress:
        """Read the persisted maintenance contract."""
        return cls(**json.loads(raw))


def legacy_progress(session: Any, ownership: str) -> MaintenanceProgress:
    """Freeze the old effective cuts once, including contexts not read yet."""
    from session.manager.models import effective_context_cursors

    last = int(session.last_consolidated)
    return MaintenanceProgress(
        ownership=ownership,
        legacy_cuts={
            "session": last,
            **effective_context_cursors(
                getattr(session, "context_cursors", None), last
            ),
        },
    )
