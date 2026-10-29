"""``AFFECTION``: relationship, loneliness and affection (P6a, D12).

The ``affection`` plugin provides this key. The host ``get``s it on every use
and does nothing when it is ``None``. State files stay at
``workspace/roles/<role_id>/state/affection.json`` and the sibling runtime
files; this key does not change their format.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from shiori_sdk.kernel import Key


class AffectionRecords(Protocol):
    """Per-role affection state and history."""

    def current_summary(
        self, role_id: str, *, now: datetime | None = None
    ) -> dict[str, Any] | None:
        """The display summary, or ``None`` while affection is uninitialized."""
        ...

    def history_page(
        self, role_id: str, *, page: int, page_size: int
    ) -> tuple[list[tuple[Any, Any]], int]:
        """One newest-first page of ``(id, entry)`` plus the total count."""
        ...

    def settle_decay(self, role_id: str, *, now: datetime | None = None) -> None:
        """Apply decay that is due. An uninitialized role is unchanged."""
        ...

    def read_state(self, role_id: str) -> Any:
        """The stored state, or ``None`` while uninitialized."""
        ...


class Affection(Protocol):
    """Relationship runtime the host calls. Delivery and turns stay in the core."""

    @property
    def affection(self) -> AffectionRecords:
        """The affection state and history of this runtime."""
        ...

    def read_snapshot(self, role_id: str) -> dict[str, Any] | None: ...

    def current_loneliness_runtime(
        self, role_id: str, *, now: datetime | None = None
    ) -> dict[str, Any] | None: ...

    def render_prompt(self, role_id: str) -> str | None:
        """The affection context block, or ``None`` while uninitialized."""
        ...

    def stage_prompts_view(self, role_id: str) -> list[dict[str, Any]]: ...

    def apply_stage_prompts(self, role_id: str, changes: Mapping[str, Any]) -> None: ...

    def handle_user_message(self, session_key: str) -> None: ...

    def handle_proactive_sent(self, session_key: str) -> None: ...

    def enrich_session_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]: ...

    async def apply_turn_affection(
        self, session_key: str, *, delta: int, reason: str
    ) -> None: ...

    def apply_scene_decision(
        self, session_key: str, transition: str, scene_key: str = ""
    ) -> None: ...

    def should_trigger_scene_followup(
        self, session_key: str, now: datetime
    ) -> tuple[bool, dict[str, Any]]: ...

    def handle_scene_followup_sent(
        self, session_key: str, occurred_at: datetime
    ) -> None: ...

    def close_scene_followup(self, session_key: str) -> None: ...

    def should_trigger_proactive(
        self, session_key: str, now: datetime
    ) -> tuple[bool, dict[str, Any]]: ...

    async def refresh_snapshot_after_consolidation(
        self, session_key: str
    ) -> dict[str, Any] | None: ...

    async def ensure_initialized(self, role_id: str) -> None:
        """Seed affection once SELF is ready. Failures propagate."""
        ...


AFFECTION: Key[Affection] = Key("affection")
"""Relationship runtime. The affection plugin provides this; the host never does."""
