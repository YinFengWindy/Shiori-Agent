"""Public host contract for communication account records and access fences."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

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
class LegacyOwnerRules:
    """Group overrides retained while an ambiguous old owner is chosen."""

    role_id: str
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
    known_capabilities: tuple[str, ...] = ()
    legacy_owner_candidates: tuple[str, ...] = ()
    legacy_owner_rules: tuple[LegacyOwnerRules, ...] = ()
    legacy_migrated: bool = False


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


@dataclass(frozen=True)
class AccountCleanup:
    """Result of a plugin delete hook after it purged its private account data.

    ``plugin_config`` is the plugin's replacement ``[plugins.<id>]`` table when
    the credential lives in host configuration; the host persists it through its
    plugin-config write path before forgetting the account. None means the
    plugin kept nothing in host configuration for this account.
    """

    plugin_config: dict[str, Any] | None = None


# A plugin delete hook receives the account's plugin-private config_ref. It must
# stop the connection, stop reporting that account, and purge every credential
# and cache it owns. Raising keeps the host record so the user can retry.
AccountDeleteHandler = Callable[[str], Awaitable[AccountCleanup]]
