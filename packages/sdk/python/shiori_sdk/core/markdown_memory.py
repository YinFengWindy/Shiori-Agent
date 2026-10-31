"""``MARKDOWN_MEMORY``: a role's Markdown memory documents on the host (#907 P6b).

Each role keeps ``MEMORY.md`` (long-term memory), ``SELF.md`` (the role's
self-understanding), ``PENDING.md`` (facts waiting to be merged into
``MEMORY.md``) and ``HISTORY.md`` (an append-only archive) under its role
directory. The files, their schema and their locations stay with the host;
this port reads and rewrites them. The host provides this key before any
plugin starts.

The port also keeps a role's memory state: plugin-owned values stored in the
role record next to the host's own initialization state. They survive
restarts and are deleted with the role.

The port does not belong to a generation; a process-level plugin resource
can keep one reference across runtime reloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from shiori_sdk.kernel import Key


class RoleMarkdownMemory(Protocol):
    """One role's Markdown memory documents and memory state.

    Merging ``PENDING.md`` into ``MEMORY.md`` is two-phase. ``snapshot_pending``
    moves the pending facts aside, so facts appended while the merge runs go
    to a new ``PENDING.md``. The merge then ends with ``commit_long_term``
    (facts are merged) or ``rollback_pending_snapshot`` (the facts go back).
    A snapshot left by a process that exited mid-merge goes back on the next
    ``snapshot_pending``.
    """

    def read_long_term(self) -> str:
        """``MEMORY.md`` as stored; empty when the document is missing."""
        ...

    def read_self(self) -> str:
        """``SELF.md`` as stored; empty when the document is missing."""
        ...

    def write_self(self, content: str) -> None:
        """Replaces ``SELF.md``; the host normalises it to the document schema."""
        ...

    def self_seed_pending(self) -> bool:
        """Whether ``SELF.md`` still waits for its first generated version.

        True while the document is a default template the host will replace
        with a version generated from the role's settings. Rewriting
        ``SELF.md`` then would read as a user edit and stop that generation.
        """
        ...

    def snapshot_pending(self) -> str:
        """Moves ``PENDING.md`` aside and returns its facts.

        Returns an empty string, and moves nothing, when no fact is pending.
        """
        ...

    def commit_long_term(self, content: str, *, history_entry: str) -> None:
        """Replaces ``MEMORY.md`` with ``content`` and drops the pending snapshot.

        A non-empty ``MEMORY.md`` is first copied to ``MEMORY.bak.md``.
        ``content`` is normalised to the document schema. A non-empty
        ``history_entry`` is appended to ``HISTORY.md`` as it is.
        """
        ...

    def rollback_pending_snapshot(self) -> None:
        """Puts the snapshot's facts back before ones appended since; no-op without one."""
        ...

    def read_state(self) -> Mapping[str, object]:
        """A copy of the plugin-owned memory state; empty once the role is deleted.

        The host's own initialization keys in the same record are left out.
        """
        ...

    def read_recent_context(self) -> str:
        """The visible ``RECENT_CONTEXT.md`` body.

        Empty when the document is missing, unstamped, or no longer visible
        to the role's current threads. The host does not recreate a deleted
        role's memory directory.
        """
        ...

    def write_state(self, key: str, value: object) -> None:
        """Stores one JSON value under ``key``; no-op once the role is deleted.

        Only ``key`` changes: other values, including ones written meanwhile,
        are kept. Raises ``ValueError`` when ``key`` is one of the host's own
        initialization keys (such as ``self_seed``) or ``value`` is not JSON
        serializable.
        """
        ...


class MarkdownMemory(Protocol):
    """Markdown memory of every role on the host."""

    @property
    def default_self(self) -> str:
        """The ``SELF.md`` template a role starts from."""
        ...

    def role(self, role_id: str) -> RoleMarkdownMemory | None:
        """The role's documents, or ``None`` when the role does not exist."""
        ...


MARKDOWN_MEMORY: Key[MarkdownMemory] = Key("markdown_memory")
"""Roles' Markdown memory documents. The host provides this."""
