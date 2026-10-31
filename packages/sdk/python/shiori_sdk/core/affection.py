"""``AFFECTION``: relationship, loneliness and affection (P6a, D12).

The ``affection`` plugin provides this key. The host ``get``s it on every use
and does nothing when it is ``None``. State files stay at
``workspace/roles/<role_id>/state/affection.json`` and the sibling runtime
files; this key does not change their format. Display data (summary,
relationship tags, loneliness) is read by the plugin's own UI through its
RPC; the host neither reads nor forwards it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from shiori_sdk.kernel import Key


class Affection(Protocol):
    """Relationship runtime the host calls. Delivery and turns stay in the core."""

    def render_prompt(self, role_id: str) -> str | None:
        """The affection context block, or ``None`` while uninitialized."""
        ...

    def handle_user_message(self, session_key: str) -> None: ...

    def handle_initiated_sent(self, session_key: str) -> None:
        """Record that an initiated reply was delivered to the role's session."""
        ...

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
