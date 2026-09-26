"""Public host contract for communication account records and access fences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConnectionState = Literal[
    "unknown", "connecting", "online", "offline", "login_required", "error"
]


@dataclass(frozen=True)
class GroupResponseRule:
    """Per-chat override preserving group-specific response and blacklist policy."""

    chat_id: str
    enabled: bool = True
    require_mention: bool = True
    blocked_sender_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountResponseRules:
    """Host-owned response policy, independent of role ownership and credentials."""

    private_enabled: bool = True
    group_enabled: bool = True
    require_mention: bool = True
    blocked_sender_ids: tuple[str, ...] = ()
    group_rules: tuple[GroupResponseRule, ...] = ()


@dataclass(frozen=True)
class AccountRecord:
    """Persisted identity; config_ref names plugin-private data, never a secret."""

    id: str
    plugin_id: str
    platform: str
    platform_account_id: str
    config_ref: str
    display_name: str = ""
    avatar_url: str = ""
    role_id: str | None = None
    ownership_version: int = 0
    response_rules: AccountResponseRules = AccountResponseRules()


@dataclass(frozen=True)
class AccountSnapshot:
    """One authoritative view shared by role scheduling and presentation."""

    record: AccountRecord
    plugin_enabled: bool
    runtime_active: bool
    connection: ConnectionState
    capabilities: frozenset[str]
    error: str = ""


@dataclass(frozen=True)
class AccountAccess:
    """Ownership fence captured before an account operation starts."""

    account_id: str
    role_id: str
    ownership_version: int
    runtime_token: str
