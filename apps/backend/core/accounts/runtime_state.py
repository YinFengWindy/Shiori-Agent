"""Generation-scoped account connection reports and operation fences."""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    AccountAccess,
    AccountDeleteHandler,
    AccountRecord,
    AccountSnapshot,
    ConnectionState,
)

DIRECT_GENERATION = "direct"
_CONNECTION_STATES = frozenset(
    {"unknown", "connecting", "online", "offline", "login_required", "error"}
)


@dataclass(frozen=True)
class _LiveReport:
    token: str
    connection: ConnectionState
    capabilities: frozenset[str]
    error: str


class AccountRuntimeState:
    """Tracks plugin generations; caller serializes access with the account lock."""

    def __init__(self) -> None:
        self._live: dict[str, dict[str, _LiveReport]] = {}
        self._last_tokens: dict[tuple[str, str], str] = {}
        self._retired_tokens: dict[tuple[str, str], set[str]] = {}
        self._enabled: dict[str, dict[str, bool]] = {}
        self._delete_handlers: dict[str, dict[str, AccountDeleteHandler]] = {}
        self.published_generation = DIRECT_GENERATION

    def set_plugin_enabled(
        self, plugin_id: str, enabled: bool, generation: str
    ) -> None:
        """Records the host's resolved manifest/config enable decision."""
        self._enabled.setdefault(generation, {})[plugin_id] = enabled

    def publish(self, generation: str) -> None:
        """Selects one prepared generation for all public account snapshots."""
        self.published_generation = generation

    def drop(self, generation: str) -> None:
        """Discards a candidate or retired generation without changing ownership."""
        self._live.pop(generation, None)
        self._enabled.pop(generation, None)
        self._delete_handlers.pop(generation, None)
        for key in [key for key in self._last_tokens if key[0] == generation]:
            del self._last_tokens[key]
        for key in [key for key in self._retired_tokens if key[0] == generation]:
            del self._retired_tokens[key]

    def set_delete_handler(
        self, plugin_id: str, handler: AccountDeleteHandler, generation: str
    ) -> None:
        """Records the one cleanup hook a plugin generation offers for its accounts."""
        handlers = self._delete_handlers.setdefault(generation, {})
        if plugin_id in handlers:
            raise ValueError(f"Account delete hook already registered: {plugin_id}")
        handlers[plugin_id] = handler

    def clear_delete_handler(
        self, plugin_id: str, handler: AccountDeleteHandler, generation: str
    ) -> None:
        """Removes a disposed plugin instance's hook, never a replacement's."""
        handlers = self._delete_handlers.get(generation, {})
        if handlers.get(plugin_id) is handler:
            del handlers[plugin_id]

    def delete_handler(self, plugin_id: str) -> AccountDeleteHandler | None:
        """Returns the published generation's hook for an enabled plugin."""
        generation = self.published_generation
        if not self._enabled.get(generation, {}).get(plugin_id, False):
            return None
        return self._delete_handlers.get(generation, {}).get(plugin_id)

    def forget(self, account_id: str) -> None:
        """Drops every generation's live report and token for a deleted account."""
        for live_accounts in self._live.values():
            live_accounts.pop(account_id, None)
        for key in [key for key in self._last_tokens if key[1] == account_id]:
            del self._last_tokens[key]
        for key in [key for key in self._retired_tokens if key[1] == account_id]:
            del self._retired_tokens[key]

    def snapshot(
        self, row: AccountRecord, *, generation: str | None = None
    ) -> AccountSnapshot:
        """Builds the shared runtime/UI view for one persisted identity."""
        active_generation = generation or self.published_generation
        live = self._live.get(active_generation, {}).get(row.id)
        return AccountSnapshot(
            row,
            self._enabled.get(active_generation, {}).get(row.plugin_id, False),
            live is not None,
            live.connection if live else "unknown",
            live.capabilities if live else frozenset(),
            live.error if live else "",
        )

    def ensure_registration_allowed(
        self, account_id: str, token: str, generation: str
    ) -> None:
        """Prevents an older instance reclaiming an account after replacement."""
        if token in self._retired_tokens.get((generation, account_id), ()):
            raise RuntimeError("Account plugin generation was superseded")

    def register(self, account_id: str, token: str, generation: str) -> None:
        """Starts or resumes one account within a plugin generation."""
        key = (generation, account_id)
        live_accounts = self._live.setdefault(generation, {})
        previous_token = self._last_tokens.get(key)
        if previous_token != token:
            if previous_token is not None:
                self._retired_tokens.setdefault(key, set()).add(previous_token)
            self._last_tokens[key] = token
        if previous_token != token or account_id not in live_accounts:
            live_accounts[account_id] = _LiveReport(token, "unknown", frozenset(), "")

    def report(
        self,
        account_id: str,
        token: str,
        generation: str,
        connection: ConnectionState,
        capabilities: frozenset[str],
        error: str,
    ) -> None:
        """Updates only the account currently owned by this plugin instance."""
        if connection not in _CONNECTION_STATES:
            raise ValueError(f"Invalid connection state: {connection}")
        live_accounts = self._live.get(generation, {})
        live = live_accounts.get(account_id)
        if live is None or live.token != token:
            raise RuntimeError("Account registration is no longer active")
        live_accounts[account_id] = _LiveReport(
            token, connection, frozenset(capabilities), error
        )

    def unregister(self, account_id: str, token: str, generation: str) -> None:
        """Stops one account while retaining its persisted identity."""
        live_accounts = self._live.get(generation, {})
        live = live_accounts.get(account_id)
        if live is not None and live.token == token:
            del live_accounts[account_id]

    def release(self, account_id: str, token: str, generation: str) -> bool:
        """Disposes an instance; returns whether it owned staged identity data."""
        self.unregister(account_id, token, generation)
        key = (generation, account_id)
        was_current = self._last_tokens.get(key) == token
        if was_current:
            del self._last_tokens[key]
        retired = self._retired_tokens.get(key)
        if retired is not None:
            retired.discard(token)
            if not retired:
                del self._retired_tokens[key]
        return was_current

    def authorize(self, row: AccountRecord, role_id: str) -> AccountAccess:
        """Captures an online, owned account for a later operation."""
        live = self._live.get(self.published_generation, {}).get(row.id)
        if (
            row.role_id != role_id
            or not self._enabled.get(self.published_generation, {}).get(
                row.plugin_id, False
            )
            or live is None
            or live.connection != "online"
        ):
            raise PermissionError("Account is not owned and online for this role")
        return AccountAccess(row.id, role_id, row.ownership_version, live.token)

    def validate_access(self, row: AccountRecord | None, access: AccountAccess) -> bool:
        """Rejects in-flight work after ownership or plugin handover."""
        live = self._live.get(self.published_generation, {}).get(access.account_id)
        return bool(
            row
            and live
            and self._enabled.get(self.published_generation, {}).get(
                row.plugin_id, False
            )
            and row.role_id == access.role_id
            and row.ownership_version == access.ownership_version
            and live.token == access.runtime_token
            and live.connection == "online"
        )
