"""Host-injected account registration and lifecycle reporting."""

from __future__ import annotations
from typing import Protocol
from .models import (
    AccountDeleteHandler,
    AccountResponseRules,
    AccountRulesHandler,
    AccountSnapshot,
    ConnectionState,
)


class AccountsCapability(Protocol):
    """Plugin-scoped registration and reporting for communication accounts.

    The plugin saves each account (identity, owner role, response rules,
    credentials) in its own storage and registers it here whenever it loads;
    the host keeps only an in-memory index of what was registered.
    """

    def register(
        self,
        *,
        platform: str,
        platform_account_id: str,
        config_ref: str,
        role_id: str | None,
        display_name: str | None = None,
        avatar_url: str | None = None,
        response_rules: "AccountResponseRules | None" = None,
    ) -> "AccountSnapshot":
        """Registers a verified identity owned by ``role_id``.

        The account ID is ``<plugin_id>:<platform_account_id>``. The owner is
        the role the account was created from, and ``response_rules`` are the
        rules the plugin saved with it; None keeps what is already indexed
        (defaults for a new account), and None display fields keep snapshots.
        ``avatar_url`` is the account's own picture as a base64 PNG, JPEG, GIF
        or WebP ``data:`` URI of at most 256 KiB, or "" for none; a remote
        URL, non-image or oversize image raises ValueError.
        """
        ...

    def register_saved(
        self,
        *,
        platform: str,
        platform_account_id: str,
        config_ref: str,
        role_id: str | None,
        display_name: str | None = None,
        avatar_url: str | None = None,
        response_rules: "AccountResponseRules | None" = None,
    ) -> "AccountSnapshot | None":
        """Registers an account restored from the plugin's own storage.

        One saved account the host refuses (no owner role, another role's
        platform account, a second account for the role) must not take the
        plugin down: the refusal is logged and listed with the plugin for the
        user to fix, and None tells the plugin not to serve that account. Its
        other accounts keep working.
        """
        ...

    def reject(self, config_ref: str, reason: str) -> None:
        """Reports a saved account the plugin cannot serve (e.g. unreadable data)."""
        ...

    def check_owner(
        self,
        *,
        config_ref: str,
        role_id: str | None,
        platform_account_id: str | None = None,
    ) -> None:
        """Raises ValueError unless ``role_id`` may own this account.

        Call it before saving account data the plugin keeps itself, so nothing
        is saved that registration would later refuse.
        """
        ...

    def role_exists(self, role_id: str) -> bool:
        """Whether an owner role still exists.

        On load a plugin deletes, with all their data, the saved accounts (and
        drafts) whose owner role is gone: role deletion only reaches plugins
        that are loaded at the time.
        """
        ...

    def report(
        self,
        account_id: str,
        *,
        connection: "ConnectionState",
        capabilities: frozenset[str] = frozenset(),
        error: str = "",
    ) -> "AccountSnapshot":
        """Reports connection, authentication, capability, or failure changes."""
        ...

    def unregister(self, account_id: str) -> None:
        """Stops one account's live presence; it stays listed while the plugin runs."""
        ...

    def on_delete(self, handler: "AccountDeleteHandler") -> None:
        """Registers the planner the host consults to delete one account.

        The handler receives the account's ``config_ref`` and returns an
        ``AccountDeletionPlan`` without side effects; the host then runs its
        idempotent ``disconnect`` and ``purge`` steps. The host also uses it
        to delete a role's accounts when the role is deleted.
        """
        ...

    def on_rules_change(self, handler: "AccountRulesHandler") -> None:
        """Registers how the plugin saves response rules edited on the host.

        The handler receives the account's ``config_ref`` and the new rules and
        must persist them with the account, so the next load registers them.
        """
        ...
