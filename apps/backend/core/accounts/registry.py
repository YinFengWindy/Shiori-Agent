"""Canonical account ownership and plugin registration service."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Callable
from uuid import uuid4

from .models import (
    AccountAccess,
    AccountRecord,
    AccountResponseRules,
    AccountSnapshot,
    ConnectionState,
)
from .persistence import ensure_unique, load_accounts, save_accounts
from .runtime_state import AccountRuntimeState, DIRECT_GENERATION


class AccountRegistry:
    """Serializes identity and ownership changes across plugin generations."""

    def __init__(
        self,
        workspace: Path,
        role_exists: Callable[[str], bool],
        *,
        lock: RLock | None = None,
    ) -> None:
        self._path = workspace / "accounts.json"
        self._role_exists = role_exists
        self._lock = lock or RLock()
        self._runtime = AccountRuntimeState()
        self._records = load_accounts(self._path, role_exists)
        self._staged_records: dict[str, dict[str, AccountRecord]] = {}

    def set_plugin_enabled(
        self, plugin_id: str, enabled: bool, *, generation: str = DIRECT_GENERATION
    ) -> None:
        """Receives the host's resolved manifest/config enable decision."""
        with self._lock:
            self._runtime.set_plugin_enabled(plugin_id, enabled, generation)

    def publish_generation(self, generation: str) -> None:
        """Commits prepared identity snapshots and publishes their live reports."""
        with self._lock:
            staged = self._staged_records.get(generation, {})
            if staged:
                updated = dict(self._records)
                for account_id, row in staged.items():
                    current = updated.get(account_id)
                    if current is not None:
                        row = replace(
                            row,
                            role_id=current.role_id,
                            ownership_version=current.ownership_version,
                            response_rules=current.response_rules,
                        )
                    updated[account_id] = row
                ensure_unique(updated)
                self._save(updated)
                del self._staged_records[generation]
            self._runtime.publish(generation)

    def drop_generation(self, generation: str) -> None:
        """Discards unpublished identity data and retired runtime state."""
        with self._lock:
            self._runtime.drop(generation)
            self._staged_records.pop(generation, None)

    def _save(self, records: dict[str, AccountRecord]) -> None:
        save_accounts(self._path, records)
        self._records = records

    def list(self, *, role_id: str | None = None) -> list[AccountSnapshot]:
        """Returns saved accounts with current, non-persisted connection reports."""
        with self._lock:
            return [
                self._runtime.snapshot(row)
                for row in self._records.values()
                if role_id is None or row.role_id == role_id
            ]

    def get(self, account_id: str) -> AccountSnapshot:
        """Returns one saved account and its current plugin report."""
        with self._lock:
            return self._runtime.snapshot(self._records[account_id])

    def register(
        self,
        *,
        plugin_id: str,
        platform: str,
        platform_account_id: str,
        config_ref: str,
        token: str,
        generation: str = DIRECT_GENERATION,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> AccountSnapshot:
        """Upserts identity; omitted display fields retain snapshots, empty ones clear."""
        fields = (plugin_id, platform, platform_account_id, config_ref, token)
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            raise ValueError(
                "Account identity, config reference, and token are required"
            )
        plugin_id, platform, platform_account_id, config_ref, token = (
            value.strip() for value in fields
        )
        with self._lock:
            staged = self._staged_records.get(generation, {})
            known = {**self._records, **staged}
            existing = next(
                (
                    row
                    for row in known.values()
                    if (row.platform, row.platform_account_id)
                    == (platform, platform_account_id)
                ),
                None,
            )
            if existing is not None and existing.plugin_id != plugin_id:
                raise ValueError("Platform account already belongs to another plugin")
            if existing is not None and existing.config_ref != config_ref:
                raise ValueError(
                    "Platform account already has another configuration reference"
                )
            if existing is not None:
                self._runtime.ensure_registration_allowed(
                    existing.id, token, generation
                )
            if any(
                row.id != (existing.id if existing else None)
                and (row.plugin_id, row.config_ref) == (plugin_id, config_ref)
                for row in known.values()
            ):
                raise ValueError(
                    "Configuration reference already belongs to an account"
                )
            row = (
                replace(
                    existing,
                    display_name=(
                        existing.display_name if display_name is None else display_name
                    ),
                    avatar_url=(
                        existing.avatar_url if avatar_url is None else avatar_url
                    ),
                )
                if existing is not None
                else AccountRecord(
                    uuid4().hex,
                    plugin_id,
                    platform,
                    platform_account_id,
                    config_ref,
                    display_name or "",
                    avatar_url or "",
                )
            )
            if row != existing:
                if generation in {
                    DIRECT_GENERATION,
                    self._runtime.published_generation,
                }:
                    self._save({**self._records, row.id: row})
                else:
                    self._staged_records.setdefault(generation, {})[row.id] = row
            self._runtime.register(row.id, token, generation)
            return self._runtime.snapshot(row, generation=generation)

    def report(
        self,
        account_id: str,
        token: str,
        *,
        generation: str = DIRECT_GENERATION,
        connection: ConnectionState,
        capabilities: frozenset[str] = frozenset(),
        error: str = "",
    ) -> AccountSnapshot:
        """Updates this plugin generation's live state for a registered account."""
        with self._lock:
            self._runtime.report(
                account_id, token, generation, connection, capabilities, error
            )
            row = self._staged_records.get(generation, {}).get(
                account_id, self._records.get(account_id)
            )
            if row is None:
                raise KeyError(account_id)
            return self._runtime.snapshot(row, generation=generation)

    def unregister(
        self, account_id: str, token: str, *, generation: str = DIRECT_GENERATION
    ) -> None:
        """Stops one account without deleting its identity or assignment."""
        with self._lock:
            self._runtime.unregister(account_id, token, generation)

    def release(
        self, account_id: str, token: str, *, generation: str = DIRECT_GENERATION
    ) -> None:
        """Reclaims a disposed plugin's runtime and unpublished identity data."""
        with self._lock:
            was_current = self._runtime.release(account_id, token, generation)
            staged = self._staged_records.get(generation)
            if was_current and staged is not None:
                staged.pop(account_id, None)
                if not staged:
                    del self._staged_records[generation]

    def assign(self, account_id: str, role_id: str | None) -> AccountSnapshot:
        """Sets the sole owner and invalidates access captured by the old owner."""
        with self._lock:
            if role_id is not None and not self._role_exists(role_id):
                raise KeyError(f"role does not exist: {role_id}")
            row = self._records[account_id]
            if row.role_id != role_id:
                row = replace(
                    row, role_id=role_id, ownership_version=row.ownership_version + 1
                )
                self._save({**self._records, account_id: row})
            return self._runtime.snapshot(row)

    def set_response_rules(
        self, account_id: str, rules: AccountResponseRules
    ) -> AccountSnapshot:
        """Persists shared response policy without changing ownership or live state."""
        with self._lock:
            row = self._records[account_id]
            if row.response_rules != rules:
                row = replace(row, response_rules=rules)
                self._save({**self._records, account_id: row})
            return self._runtime.snapshot(row)

    def unassign_role(self, role_id: str) -> None:
        """Keeps account records when a role is deleted."""
        with self._lock:
            updated = {
                account_id: (
                    replace(
                        row, role_id=None, ownership_version=row.ownership_version + 1
                    )
                    if row.role_id == role_id
                    else row
                )
                for account_id, row in self._records.items()
            }
            if updated != self._records:
                self._save(updated)

    def authorize(self, account_id: str, role_id: str) -> AccountAccess:
        """Captures an online, owned account for a later operation."""
        with self._lock:
            return self._runtime.authorize(self._records[account_id], role_id)

    def validate_access(self, access: AccountAccess) -> bool:
        """Rejects an in-flight operation after ownership or plugin handover."""
        with self._lock:
            return self._runtime.validate_access(
                self._records.get(access.account_id), access
            )
