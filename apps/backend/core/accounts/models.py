"""Public host contract for communication account records and access fences.

Plugins own every account record (identity, owner role, response rules,
credentials) in their own storage; the host only keeps an in-memory index of
the accounts its loaded plugins registered.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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
    """How an account responds; saved by its plugin, applied by host routing."""

    private_enabled: bool = True
    group_enabled: bool = True
    require_mention: bool = True
    blocked_sender_ids: tuple[str, ...] = ()
    group_rules: tuple[GroupResponseRule, ...] = ()


def account_id_for(plugin_id: str, platform_account_id: str) -> str:
    """The deterministic account ID: ``<plugin_id>:<platform_account_id>``.

    Derived from the identity alone, so deleting and re-adding the same
    platform account yields the same ID and its history stays attached.
    """
    return f"{plugin_id}:{platform_account_id}"


@dataclass(frozen=True)
class AccountRecord:
    """One registered account; config_ref names plugin-private data, never a secret."""

    id: str
    plugin_id: str
    platform: str
    platform_account_id: str
    config_ref: str
    role_id: str
    display_name: str = ""
    avatar_url: str = ""
    response_rules: AccountResponseRules = AccountResponseRules()


@dataclass(frozen=True)
class AccountSnapshot:
    """One authoritative view shared by role scheduling and presentation."""

    record: AccountRecord
    runtime_active: bool
    connection: ConnectionState
    capabilities: frozenset[str]
    error: str = ""


@dataclass(frozen=True)
class AccountAccess:
    """Ownership fence captured before an account operation starts."""

    account_id: str
    role_id: str
    runtime_token: str


class AccountNotFoundError(KeyError):
    """No loaded plugin has registered the requested account."""


class AccountDeletingError(RuntimeError):
    """The account is being deleted; its identity and settings are frozen."""


@dataclass(frozen=True)
class AccountDeletionPlan:
    """A plugin's side-effect-free plan for deleting one of its accounts.

    The host runs ``disconnect`` then ``purge``, then drops the account from
    its index. Both steps must be idempotent, and planning must still work
    after a purge, so a failed deletion can simply be retried.
    """

    # Stops the connection and all reports for the account; keeps its data.
    disconnect: Callable[[], Awaitable[None]]
    # Deletes the plugin's record, credentials, caches, and private files.
    purge: Callable[[], Awaitable[None]]


# A plugin delete hook receives the account's plugin-private config_ref and
# returns its plan without side effects; raising aborts before anything changes.
AccountDeleteHandler = Callable[[str], AccountDeletionPlan]

# A plugin rules hook durably saves new response rules for the account behind
# ``config_ref`` in the plugin's own storage; raising leaves the rules unchanged.
AccountRulesHandler = Callable[[str, AccountResponseRules], None]
