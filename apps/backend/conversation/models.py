from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContactRecord:
    """Conversation contact row stored in `contacts`."""

    id: str
    role_id: str
    kind: str
    channel: str
    external_id: str
    display_name: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ThreadRecord:
    """Conversation thread row stored in `threads`."""

    id: str
    role_id: str
    contact_id: str
    channel: str
    thread_kind: str
    external_thread_id: str
    legacy_session_key: str
    archived: bool
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StateRecord:
    """Projected state row shared by thread/contact/role state tables."""

    owner_id: str
    summary: str
    metadata: dict[str, Any]
    updated_at: str
