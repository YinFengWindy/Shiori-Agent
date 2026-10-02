"""Durable, independent memory/consumer versions and model window progress."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
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


def message_window_key(message: dict, user_threads: UserContextThreads | None) -> str:
    """The window a persisted message belongs to under the given binding."""
    from session.manager.models import message_thread_id

    if user_threads is None:
        return "session"
    thread_id = message_thread_id(message)
    return "user" if user_threads.contains(thread_id) else "external:" + thread_id


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


# Model-window state; undo keeps it while resetting memory/consumer progress.
_WINDOW_FIELDS = (
    "legacy_cuts",
    "windows",
    "window_versions",
    "compaction_counts",
    "summaries",
    "summary_source_ids",
)


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
    generation: int = 0
    memory_version: int = 0
    recent_context_version: int = 0
    recent_context_source_ids: list[str] = field(default_factory=list)
    published_version: int = 0
    relationship_version: int = 0
    consumer_error: str = ""
    pending_consumers: dict[str, Any] = field(default_factory=dict)

    def invalidated(self, *, keep_windows: bool = False) -> MaintenanceProgress:
        """Return a new generation without mutating the previous state snapshot.

        Memory/consumer progress always restarts. An explicit clear voids the
        windows too; undo passes ``keep_windows`` after invalidating only the
        windows its deletion affected.
        """
        reset = MaintenanceProgress(
            ownership=self.ownership,
            generation=self.generation + 1,
            memory_version=self.memory_version + 1,
        )
        if not keep_windows:
            return reset
        kept = MaintenanceProgress.load(self.dump())
        return replace(reset, **{name: getattr(kept, name) for name in _WINDOW_FIELDS})

    def without_windows(self, keys: set[str]) -> MaintenanceProgress:
        """Return a copy whose ``keys`` windows restart at 0 with no summary.

        Other windows, frozen legacy cuts and memory/consumer progress stay. An
        explicit 0 overrides the legacy cut, which predates the invalidation.
        """
        progress = MaintenanceProgress.load(self.dump())
        for key in keys:
            progress.windows[key] = 0
            progress.summaries.pop(key, None)
            progress.summary_source_ids.pop(key, None)
            progress.window_versions[key] = self.window_versions.get(key, 0) + 1
        return progress

    def rebound(self, ownership: str) -> MaintenanceProgress:
        """Adopt a new identity binding as a new generation.

        The unscoped session window, the shared user window and external
        threads that entered or left the user context lose their window; memory
        cursors and consumer progress are kept, so the new ownership only
        applies to later consolidation.
        """
        before = set(json.loads(self.ownership)) if self.ownership else set()
        after = set(json.loads(ownership)) if ownership else set()
        progress = self.without_windows(
            {
                "session",
                "user",
                *("external:" + thread_id for thread_id in before ^ after),
            }
        )
        progress.ownership = ownership
        progress.generation += 1
        return progress

    def under(self, ownership: str) -> MaintenanceProgress:
        """The single normalization: this state as seen under ``ownership``."""
        return self if self.ownership == ownership else self.rebound(ownership)

    def cut(self, key: str) -> int:
        """Effective cut of window ``key``: its own window or the frozen legacy cut."""
        return self.windows.get(key, self.legacy_cuts.get(key.partition(":")[0], 0))

    def cursor(self, view: ContextView | None) -> int:
        """Read the effective window cut under the view's current binding."""
        return self.under(ownership_key(view.user_threads if view else None)).cut(
            window_key(view)
        )

    def dump(self) -> str:
        """Serialize the owner state independently from ordinary session metadata."""
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def load(cls, raw: str) -> MaintenanceProgress:
        """Read the persisted maintenance contract.

        ``request_owners`` bound windows to a model before #603; windows are
        model independent now, so the stale field is dropped on read.
        """
        data = json.loads(raw)
        data.pop("request_owners", None)
        return cls(**data)


def effective_progress(
    session: Any, user_threads: UserContextThreads | None
) -> MaintenanceProgress:
    """Read a session's progress under the current binding without mutating it.

    The cached ``maintenance_progress`` only mirrors persisted state; legacy
    migration and rebinding are derived here, identically for every reader.
    """
    stamp = ownership_key(user_threads)
    stored = getattr(session, "maintenance_progress", None)
    return (stored or legacy_progress(session, stamp)).under(stamp)


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
