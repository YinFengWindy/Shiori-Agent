"""Generation-scoped account index: registered records, live reports, fences."""

from __future__ import annotations

from dataclasses import dataclass, field

from shiori_sdk.accounts.models import (
    AccountAccess,
    AccountDeleteHandler,
    AccountRecord,
    AccountRulesHandler,
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


@dataclass
class _Generation:
    """Everything one plugin generation told the host about its accounts."""

    # Accounts a live plugin instance of this generation registered.
    records: dict[str, AccountRecord] = field(default_factory=dict)
    live: dict[str, _LiveReport] = field(default_factory=dict)
    # Current and superseded plugin-instance tokens per account.
    last_tokens: dict[str, str] = field(default_factory=dict)
    retired_tokens: dict[str, set[str]] = field(default_factory=dict)
    delete_handlers: dict[str, AccountDeleteHandler] = field(default_factory=dict)
    rules_handlers: dict[str, AccountRulesHandler] = field(default_factory=dict)
    # Saved accounts a plugin could not register, per plugin.
    rejected: dict[str, list[str]] = field(default_factory=dict)


class AccountRuntimeState:
    """Tracks plugin generations; caller serializes access with the account lock.

    Nothing here is persisted: a generation's index is rebuilt by its plugins
    registering their own saved accounts, and a plugin that is disabled or not
    loaded simply has no accounts in it.
    """

    def __init__(self) -> None:
        self._generations: dict[str, _Generation] = {}
        self.published_generation = DIRECT_GENERATION

    def generation(self, generation: str) -> _Generation:
        """Returns (creating on first use) one generation's index."""
        return self._generations.setdefault(generation, _Generation())

    @property
    def published(self) -> _Generation:
        """The generation whose accounts routing, sending and the UI see."""
        return self.generation(self.published_generation)

    def publish(self, generation: str) -> None:
        """Selects one prepared generation for all public account snapshots."""
        self.published_generation = generation

    def drop(self, generation: str) -> None:
        """Discards a candidate or retired generation's whole index."""
        self._generations.pop(generation, None)

    def generations(self) -> list[_Generation]:
        """Every generation still holding an index, published or not."""
        return list(self._generations.values())

    def forget(self, account_id: str) -> None:
        """Drops a deleted account from every generation's index."""
        for state in self._generations.values():
            state.records.pop(account_id, None)
            state.live.pop(account_id, None)
            state.last_tokens.pop(account_id, None)
            state.retired_tokens.pop(account_id, None)

    def snapshot(
        self, row: AccountRecord, *, generation: str | None = None
    ) -> AccountSnapshot:
        """Builds the shared runtime/UI view for one registered account."""
        state = self.generation(generation or self.published_generation)
        live = state.live.get(row.id)
        return AccountSnapshot(
            row,
            live is not None,
            live.connection if live else "unknown",
            live.capabilities if live else frozenset(),
            live.error if live else "",
        )

    def ensure_registration_allowed(
        self, account_id: str, token: str, generation: str
    ) -> None:
        """Prevents an older instance reclaiming an account after replacement."""
        if token in self.generation(generation).retired_tokens.get(account_id, ()):
            raise RuntimeError("Account plugin generation was superseded")

    def register(self, row: AccountRecord, token: str, generation: str) -> None:
        """Indexes one account and starts or resumes it within a generation."""
        state = self.generation(generation)
        state.records[row.id] = row
        previous_token = state.last_tokens.get(row.id)
        if previous_token != token:
            if previous_token is not None:
                state.retired_tokens.setdefault(row.id, set()).add(previous_token)
            state.last_tokens[row.id] = token
        if previous_token != token or row.id not in state.live:
            state.live[row.id] = _LiveReport(token, "unknown", frozenset(), "")

    def report(
        self,
        account_id: str,
        token: str,
        generation: str,
        connection: ConnectionState,
        capabilities: frozenset[str],
        error: str,
    ) -> AccountRecord:
        """Updates only the account currently owned by this plugin instance."""
        if connection not in _CONNECTION_STATES:
            raise ValueError(f"Invalid connection state: {connection}")
        state = self.generation(generation)
        live = state.live.get(account_id)
        if live is None or live.token != token:
            raise RuntimeError("Account registration is no longer active")
        state.live[account_id] = _LiveReport(
            token, connection, frozenset(capabilities), error
        )
        return state.records[account_id]

    def unregister(self, account_id: str, token: str, generation: str) -> None:
        """Stops one account's live presence; it stays listed while its plugin runs."""
        state = self.generation(generation)
        live = state.live.get(account_id)
        if live is not None and live.token == token:
            del state.live[account_id]

    def release(self, account_id: str, token: str, generation: str) -> None:
        """Disposes a plugin instance: its account leaves that generation's index."""
        self.unregister(account_id, token, generation)
        state = self.generation(generation)
        if state.last_tokens.get(account_id) == token:
            del state.last_tokens[account_id]
            state.records.pop(account_id, None)
        retired = state.retired_tokens.get(account_id)
        if retired is not None:
            retired.discard(token)
            if not retired:
                del state.retired_tokens[account_id]

    def authorize(self, row: AccountRecord, role_id: str) -> AccountAccess:
        """Captures an online, owned account for a later operation."""
        live = self.published.live.get(row.id)
        if row.role_id != role_id or live is None or live.connection != "online":
            raise PermissionError("Account is not owned and online for this role")
        return AccountAccess(row.id, role_id, live.token)

    def validate_access(self, access: AccountAccess) -> bool:
        """Rejects in-flight work after deletion or plugin handover."""
        state = self.published
        row = state.records.get(access.account_id)
        live = state.live.get(access.account_id)
        return bool(
            row
            and live
            and row.role_id == access.role_id
            and live.token == access.runtime_token
            and live.connection == "online"
        )
