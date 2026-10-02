"""Account capability fake with explicitly seeded role availability and registrations."""

from dataclasses import replace
from collections.abc import Callable

from shiori_sdk.accounts import (
    AccountRecord,
    AccountResponseRules,
    AccountSnapshot,
    ConnectionState,
    AccountDeleteHandler,
    AccountRulesHandler,
    account_id_for,
)
from shiori_sdk.accounts.capability import AccountsCapability


class FakeAccounts:
    """Record registration, reports and hooks without loading an account registry."""

    def __init__(
        self, plugin_id: str = "test", *, id_factory: Callable[[str], str] | None = None
    ):
        self.plugin_id = plugin_id
        self.id_factory = id_factory or (lambda value: account_id_for(plugin_id, value))
        self.available_roles: set[str] | None = None
        self.records: dict[str, AccountSnapshot] = {}
        self.roles: dict[str, str] = {}
        self.avatars: dict[str, str] = {}
        self.reports: list[tuple[str, dict[str, object]]] = []
        self.rejections: list[tuple[str, str]] = []
        self.delete_handler: AccountDeleteHandler | None = None
        self.rules_handler: AccountRulesHandler | None = None

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
        """Record a public snapshot for a test-provided identity."""
        self.check_owner(
            config_ref=config_ref,
            role_id=role_id,
            platform_account_id=platform_account_id,
        )
        if role_id is None:
            raise ValueError("账号没有所属角色")
        account_id = self.id_factory(platform_account_id)
        previous = self.records.get(account_id)
        record = AccountRecord(
            account_id,
            self.plugin_id,
            platform,
            platform_account_id,
            config_ref,
            role_id,
            (
                display_name
                if display_name is not None
                else (previous.record.display_name if previous else "")
            ),
            (
                avatar_url
                if avatar_url is not None
                else (previous.record.avatar_url if previous else "")
            ),
            (
                response_rules
                if response_rules is not None
                else (
                    previous.record.response_rules
                    if previous
                    else AccountResponseRules()
                )
            ),
        )
        snapshot = (
            replace(previous, record=record)
            if previous
            else AccountSnapshot(record, True, "unknown", frozenset())
        )
        self.records[account_id] = snapshot
        self.roles[platform_account_id] = role_id
        self.avatars[platform_account_id] = record.avatar_url
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
        """Reject a fixture's unavailable role without serving the account."""
        if not role_id or not self.role_exists(role_id):
            self.reject(config_ref, "账号没有所属角色")
            return None
        return self.register(
            platform=platform,
            platform_account_id=platform_account_id,
            config_ref=config_ref,
            role_id=role_id,
            display_name=display_name,
            avatar_url=avatar_url,
            response_rules=response_rules,
        )

    def check_owner(
        self,
        *,
        config_ref: str,
        role_id: str | None,
        platform_account_id: str | None = None,
    ) -> None:
        """Refuse fixture roles absent from the explicitly seeded role set."""
        if not role_id or not self.role_exists(role_id):
            raise ValueError("账号没有所属角色")

    def role_exists(self, role_id: str) -> bool:
        """Read fixture availability."""
        return self.available_roles is None or role_id in self.available_roles

    def report(
        self,
        account_id: str,
        *,
        connection: ConnectionState,
        capabilities: frozenset[str] = frozenset(),
        error: str = "",
    ) -> AccountSnapshot:
        """Record exactly the identity and status reported by the plugin."""
        self.reports.append(
            (
                account_id,
                {
                    "connection": connection,
                    "capabilities": capabilities,
                    "error": error,
                },
            )
        )
        self.records[account_id] = replace(
            self.records[account_id],
            connection=connection,
            capabilities=capabilities,
            error=error,
        )
        return self.records[account_id]

    def reject(self, config_ref: str, reason: str) -> None:
        """Record a plugin's rejected saved account."""
        self.rejections.append((config_ref, reason))

    def unregister(self, account_id: str) -> None:
        """Retire a fixture account without deleting its stored plugin data."""
        self.records[account_id] = replace(
            self.records[account_id], runtime_active=False
        )

    def on_delete(self, handler: AccountDeleteHandler) -> None:
        """Record deletion planning."""
        self.delete_handler = handler

    def on_rules_change(self, handler: AccountRulesHandler) -> None:
        """Record the persistence callback for response rules."""
        self.rules_handler = handler

    def as_capability(self) -> AccountsCapability:
        """Check fixture and host against the same injected contract."""
        return self
