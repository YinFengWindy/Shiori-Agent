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


class AccountNotFoundError(LookupError):
    """The requested account has no host record."""


class AccountDeletingError(RuntimeError):
    """The account is being deleted; its identity and settings are frozen."""


@dataclass(frozen=True)
class AccountDeletionPlan:
    """A plugin's side-effect-free plan for deleting one of its accounts.

    The host runs it in order: validate ``plugin_config``, ``disconnect``,
    ``purge``, persist ``plugin_config``, then forget its record. Both steps
    must be idempotent, and planning must still work after a purge, so a
    failed deletion can simply be retried.
    """

    # Stops the connection and all reports for the account; keeps its data.
    disconnect: Callable[[], Awaitable[None]]
    # Deletes the plugin's credentials, caches, and private files.
    purge: Callable[[], Awaitable[None]]
    # Replacement ``[plugins.<id>]`` table (unexpanded values) when the
    # credential lives in host configuration; None leaves config untouched.
    plugin_config: dict[str, Any] | None = None


# A plugin delete hook receives the account's plugin-private config_ref and
# returns its plan without side effects; raising aborts before anything changes.
AccountDeleteHandler = Callable[[str], AccountDeletionPlan]
