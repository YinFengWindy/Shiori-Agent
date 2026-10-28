"""The ``accounts`` service: communication accounts in the ``AccountRegistry``.

``PluginAccounts`` is the ``ACCOUNTS`` core service of one plugin kernel
generation. Plugins register into that generation's own account index, which
the host publishes when the generation becomes the running one.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from shiori_sdk.accounts.models import (
    AccountDeleteHandler,
    AccountResponseRules,
    AccountRulesHandler,
    AccountSnapshot,
    ConnectionState,
)
from shiori_sdk.accounts.routing import AccountRoute

from shiori_sdk.core.services import ACCOUNTS
from shiori_sdk.kernel import Kernel

from agent.plugin_host.core_keys import PluginBinding, required_core_key
from core.accounts.registry import AccountRegistry

logger = logging.getLogger(__name__)


def publish_plugin_accounts(kernel: Kernel) -> None:
    """Makes ``kernel``'s account index the one routing, sending and the UI see.

    Loading a generation only registers accounts. The app publishes when it
    starts, and a settings reload publishes when its pointer switches.
    """
    _plugin_accounts(kernel).publish()


def drop_plugin_accounts(kernel: Kernel) -> None:
    """Discards ``kernel``'s account index after its plugins have stopped."""
    _plugin_accounts(kernel).drop()


def _plugin_accounts(kernel: Kernel) -> PluginAccounts:
    """The generation's ``ACCOUNTS`` provider, which the host always assembles.

    The key is typed as the SDK protocol; the host stores ``PluginAccounts``
    under it, so anything else is an assembly error, not a skip.
    """
    accounts = required_core_key(kernel.get, ACCOUNTS)
    if not isinstance(accounts, PluginAccounts):
        raise TypeError(f"ACCOUNTS 应由 PluginAccounts 提供，实际是 {type(accounts)!r}")
    return accounts


class PluginAccounts:
    """The ``ACCOUNTS`` core service: one generation's view of the registry."""

    def __init__(self, registry: AccountRegistry) -> None:
        self._registry = registry
        self._generation = uuid4().hex

    def for_plugin(self, binding: PluginBinding) -> AccountsCapability:
        """The accounts capability of the plugin ``binding`` describes."""
        return AccountsCapability(self._registry, binding, self._generation)

    def publish(self) -> None:
        """Makes this generation's account reports authoritative."""
        self._registry.publish_generation(self._generation)

    def drop(self) -> None:
        """Discards this generation's account index."""
        self._registry.drop_generation(self._generation)


class AccountsCapability:
    """Plugin-scoped registration and reporting for communication accounts.

    The plugin saves each account (identity, owner role, response rules,
    credentials) in its own storage and registers it here whenever it loads;
    the host keeps only an in-memory index of what was registered.
    """

    def __init__(
        self, registry: AccountRegistry, binding: PluginBinding, generation: str
    ) -> None:
        self._registry = registry
        self._effects = binding.scope
        self._plugin_id = binding.plugin_id
        self._generation = generation
        self._token = uuid4().hex
        self._registered: set[str] = set()

    def register(
        self,
        *,
        platform: str,
        platform_account_id: str,
        config_ref: str,
        role_id: str | None,
        display_name: str | None = None,
        avatar_url: str | None = None,
        response_rules: AccountResponseRules | None = None,
    ) -> AccountSnapshot:
        """Registers a verified identity owned by ``role_id``.

        The account ID is ``<plugin_id>:<platform_account_id>``. The owner is
        the role the account was created from, and ``response_rules`` are the
        rules the plugin saved with it; None keeps what is already indexed
        (defaults for a new account), and None display fields keep snapshots.
        ``avatar_url`` is the account's own picture as a base64 PNG, JPEG, GIF
        or WebP ``data:`` URI of at most 256 KiB, or "" for none; a remote
        URL, non-image or oversize image raises ValueError.
        """
        self._effects.ensure_active("account:register")
        snapshot = self._registry.register(
            plugin_id=self._plugin_id,
            platform=platform,
            platform_account_id=platform_account_id,
            config_ref=config_ref,
            token=self._token,
            role_id=role_id,
            generation=self._generation,
            display_name=display_name,
            avatar_url=avatar_url,
            response_rules=response_rules,
        )
        account_id = snapshot.record.id
        if account_id not in self._registered:
            self._registered.add(account_id)
            _ = self._effects.effect(
                lambda: self._registry.release(
                    account_id, self._token, generation=self._generation
                ),
                f"account:{account_id}",
            )
        return snapshot

    def register_saved(
        self,
        *,
        platform: str,
        platform_account_id: str,
        config_ref: str,
        role_id: str | None,
        display_name: str | None = None,
        avatar_url: str | None = None,
        response_rules: AccountResponseRules | None = None,
    ) -> AccountSnapshot | None:
        """Registers an account restored from the plugin's own storage.

        One saved account the host refuses (no owner role, another role's
        platform account, a second account for the role) must not take the
        plugin down: the refusal is logged and listed with the plugin for the
        user to fix, and None tells the plugin not to serve that account. Its
        other accounts keep working.
        """
        try:
            return self.register(
                platform=platform,
                platform_account_id=platform_account_id,
                config_ref=config_ref,
                role_id=role_id,
                display_name=display_name,
                avatar_url=avatar_url,
                response_rules=response_rules,
            )
        except ValueError as exc:
            self.reject(config_ref, str(exc))
            return None

    def reject(self, config_ref: str, reason: str) -> None:
        """Reports a saved account the plugin cannot serve (e.g. unreadable data)."""
        message = f"账号 {config_ref} 未加载：{reason}"
        logger.error("插件 %s 的%s", self._plugin_id, message)
        self._registry.reject(self._plugin_id, message, generation=self._generation)

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
        self._registry.check_owner(
            plugin_id=self._plugin_id,
            config_ref=config_ref,
            role_id=role_id,
            platform_account_id=platform_account_id,
            generation=self._generation,
        )

    def role_exists(self, role_id: str) -> bool:
        """Whether an owner role still exists.

        On load a plugin deletes, with all their data, the saved accounts (and
        drafts) whose owner role is gone: role deletion only reaches plugins
        that are loaded at the time.
        """
        return self._registry.role_exists(role_id)

    def report(
        self,
        account_id: str,
        *,
        connection: ConnectionState,
        capabilities: frozenset[str] = frozenset(),
        error: str = "",
        tool_conversation: AccountRoute | None = None,
    ) -> AccountSnapshot:
        """Reports connection, authentication, capability, or failure changes."""
        self._effects.ensure_active(f"account:{account_id}:report")
        if account_id not in self._registered:
            raise PermissionError("Account was not registered by this plugin instance")
        return self._registry.report(
            account_id,
            self._token,
            generation=self._generation,
            connection=connection,
            capabilities=capabilities,
            error=error,
            tool_conversation=tool_conversation,
        )

    def unregister(self, account_id: str) -> None:
        """Stops one account's live presence; it stays listed while the plugin runs."""
        self._effects.ensure_active(f"account:{account_id}:unregister")
        if account_id not in self._registered:
            raise PermissionError("Account was not registered by this plugin instance")
        self._registry.unregister(account_id, self._token, generation=self._generation)

    def on_delete(self, handler: AccountDeleteHandler) -> None:
        """Registers the planner the host consults to delete one account.

        The handler receives the account's ``config_ref`` and returns an
        ``AccountDeletionPlan`` without side effects; the host then runs its
        idempotent ``disconnect`` and ``purge`` steps. The host also uses it
        to delete a role's accounts when the role is deleted.
        """
        self._effects.ensure_active("account:delete_hook")
        self._registry.set_delete_handler(
            self._plugin_id, handler, generation=self._generation
        )
        _ = self._effects.effect(
            lambda: self._registry.clear_delete_handler(
                self._plugin_id, handler, generation=self._generation
            ),
            "account:delete_hook",
        )

    def on_rules_change(self, handler: AccountRulesHandler) -> None:
        """Registers how the plugin saves response rules edited on the host.

        The handler receives the account's ``config_ref`` and the new rules and
        must persist them with the account, so the next load registers them.
        """
        self._effects.ensure_active("account:rules_hook")
        self._registry.set_rules_handler(
            self._plugin_id, handler, generation=self._generation
        )
        _ = self._effects.effect(
            lambda: self._registry.clear_rules_handler(
                self._plugin_id, handler, generation=self._generation
            ),
            "account:rules_hook",
        )
