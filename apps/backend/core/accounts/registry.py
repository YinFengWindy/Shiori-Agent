"""Canonical account ownership and plugin registration service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from .models import (
    AccountAccess,
    AccountConfigReader,
    AccountDeleteHandler,
    AccountDeletingError,
    AccountNotFoundError,
    AccountRecord,
    AccountResponseRules,
    AccountSnapshot,
    ConnectionState,
    GroupResponseRule,
    LegacyOwnerRules,
)
from .persistence import ensure_unique, load_accounts, save_accounts
from .runtime_state import AccountRuntimeState, DIRECT_GENERATION

if TYPE_CHECKING:
    from core.roles.models import RoleRecord


class AccountRegistry:
    """Serializes identity and ownership changes across plugin generations."""

    def __init__(
        self,
        workspace: Path,
        role_exists: Callable[[str], bool],
        *,
        lock: RLock | None = None,
        legacy_roles: Callable[[], list[RoleRecord]] | None = None,
        retire_legacy_bindings: Callable[[set[str]], None] | None = None,
    ) -> None:
        self._path = workspace / "accounts.json"
        self._role_exists = role_exists
        self._legacy_roles = legacy_roles
        self._retire_legacy_bindings = retire_legacy_bindings
        self._lock = lock or RLock()
        self._runtime = AccountRuntimeState()
        self._records = load_accounts(self._path, role_exists)
        self._staged_records: dict[str, dict[str, AccountRecord]] = {}
        self._delete_lock = asyncio.Lock()
        # Accounts mid-deletion; ownership and rules are frozen until it ends.
        self._deleting: set[str] = set()

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
            self.migrate_legacy_bindings()

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
        role_id: str | None,
        generation: str = DIRECT_GENERATION,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> AccountSnapshot:
        """Upserts an owned identity; omitted display fields retain snapshots.

        Every account belongs to exactly one role from creation on; the
        ownership rule is ``_ownership_refusal``.
        """
        fields = (plugin_id, platform, platform_account_id, config_ref, token)
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            raise ValueError("账号身份、配置引用和运行令牌不能为空")
        plugin_id, platform, platform_account_id, config_ref, token = (
            value.strip() for value in fields
        )
        with self._lock:
            staged = self._staged_records.get(generation, {})
            known = {**self._records, **staged}
            refusal = self._ownership_refusal(
                known,
                plugin_id=plugin_id,
                config_ref=config_ref,
                role_id=role_id,
                identity=(platform, platform_account_id),
            )
            if refusal is not None:
                raise ValueError(refusal)
            existing = next(
                (
                    row
                    for row in known.values()
                    if (row.platform, row.platform_account_id)
                    == (platform, platform_account_id)
                ),
                None,
            )
            if existing is not None:
                # A concurrent generation must not revive an account mid-delete.
                self._ensure_not_deleting(existing.id)
                self._runtime.ensure_registration_allowed(
                    existing.id, token, generation
                )
            if any(
                row.id != (existing.id if existing else None)
                and (row.plugin_id, row.config_ref) == (plugin_id, config_ref)
                for row in known.values()
            ):
                raise ValueError("配置引用已属于另一个账号")
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
                    role_id=(role_id or "").strip(),
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
            if generation == DIRECT_GENERATION:
                self.migrate_legacy_bindings()
                row = self._records[row.id]
            return self._runtime.snapshot(row, generation=generation)

    def _ownership_refusal(
        self,
        known: dict[str, AccountRecord],
        *,
        plugin_id: str,
        config_ref: str,
        role_id: str | None,
        identity: tuple[str, str] | None,
    ) -> str | None:
        """The one ownership rule; returns why ``role_id`` may not hold this account.

        The owner must be an existing role; a platform account belongs to one
        plugin entry and one role (an unowned old record is never taken over);
        and a role holds at most one account per plugin. Without a known
        identity the account is found by its plugin configuration reference.
        """
        if not role_id or not role_id.strip():
            return "账号没有所属角色"
        role_id = role_id.strip()
        if not self._role_exists(role_id):
            return f"角色不存在：{role_id}"
        existing = next(
            (
                row
                for row in known.values()
                if (
                    (row.platform, row.platform_account_id) == identity
                    if identity is not None
                    else (row.plugin_id, row.config_ref) == (plugin_id, config_ref)
                )
            ),
            None,
        )
        if existing is not None:
            if existing.plugin_id != plugin_id:
                return "平台账号已属于另一个插件"
            if existing.config_ref != config_ref:
                return "平台账号已作为另一个账号添加"
            if existing.role_id is None:
                return "平台账号存在未归属的旧记录，请先手动清理"
            if existing.role_id != role_id:
                return "平台账号已属于另一个角色"
        if any(
            row.id != (existing.id if existing else None)
            and (row.role_id, row.plugin_id) == (role_id, plugin_id)
            for row in known.values()
        ):
            return "该角色在这个渠道已有账号"
        return None

    def check_owner(
        self,
        *,
        plugin_id: str,
        config_ref: str,
        role_id: str | None,
        platform: str | None = None,
        platform_account_id: str | None = None,
    ) -> None:
        """Raises ValueError unless ``role_id`` may hold this account.

        Plugins call it before saving account data of their own, so nothing is
        saved that a later registration would refuse.
        """
        with self._lock:
            refusal = self._ownership_refusal(
                self._records,
                plugin_id=plugin_id,
                config_ref=config_ref,
                role_id=role_id,
                identity=(
                    (platform, platform_account_id)
                    if platform and platform_account_id
                    else None
                ),
            )
        if refusal is not None:
            raise ValueError(refusal)

    def set_config_reader(
        self,
        plugin_id: str,
        reader: AccountConfigReader,
        *,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Accepts one plugin generation's reader for accounts in its config table."""
        with self._lock:
            self._runtime.set_config_reader(plugin_id, reader, generation)

    def clear_config_reader(
        self,
        plugin_id: str,
        reader: AccountConfigReader,
        *,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Withdraws a disposed plugin instance's config reader."""
        with self._lock:
            self._runtime.clear_config_reader(plugin_id, reader, generation)

    def check_config_write(
        self, plugin_id: str, before: dict[str, Any], after: dict[str, Any]
    ) -> None:
        """Refuses a ``[plugins.<id>]`` write that would declare an unusable account.

        Both tables are resolved values. An entry keeps its owner for good; a
        new or changed entry must pass the ownership rule, also against the
        other entries of the same write. Unchanged entries are left as they
        are, so older ownerless data stays unusable until cleaned by hand. A
        plugin that is not running cannot read its table, so nothing is checked.
        """
        reader = self._runtime.config_reader(plugin_id)
        if reader is None:
            return
        try:
            previous = {claim.config_ref: claim for claim in reader(before)}
        except ValueError:
            # A table that does not even parse declares no usable account.
            previous = {}
        claims = reader(after)
        with self._lock:
            for claim in claims:
                old = previous.get(claim.config_ref)
                if old is not None and old.role_id != claim.role_id:
                    raise ValueError(f"账号 {claim.config_ref} 的所属角色不能更改")
                if old == claim:
                    continue
                identity = (
                    (claim.platform, claim.platform_account_id)
                    if claim.platform and claim.platform_account_id
                    else None
                )
                refusal = self._ownership_refusal(
                    self._records,
                    plugin_id=plugin_id,
                    config_ref=claim.config_ref,
                    role_id=claim.role_id,
                    identity=identity,
                )
                if refusal is None and any(
                    other is not claim
                    and (
                        other.role_id == claim.role_id
                        or (
                            identity is not None
                            and (other.platform, other.platform_account_id) == identity
                        )
                    )
                    for other in claims
                ):
                    refusal = (
                        "该角色在这个渠道已有账号"
                        if any(
                            other is not claim and other.role_id == claim.role_id
                            for other in claims
                        )
                        else "平台账号已作为另一个账号添加"
                    )
                if refusal is not None:
                    raise ValueError(f"账号 {claim.config_ref}：{refusal}")

    def reject(
        self, plugin_id: str, message: str, *, generation: str = DIRECT_GENERATION
    ) -> None:
        """Records a saved account a plugin generation could not register."""
        with self._lock:
            self._runtime.reject(plugin_id, message, generation)

    def rejected(self, plugin_id: str) -> list[str]:
        """Saved accounts the running plugin could not register, with reasons."""
        with self._lock:
            return self._runtime.rejected(plugin_id)

    def migrate_legacy_bindings(self) -> None:
        """Import saved role ownership and group policy after accounts are known."""
        if self._legacy_roles is None:
            return
        with self._lock:
            roles = self._legacy_roles()
            updated = dict(self._records)
            migrated_platforms: set[str] = set()
            for row in self._records.values():
                platform_accounts = [
                    item
                    for item in self._records.values()
                    if item.platform == row.platform
                ]
                bindings = [
                    (role.id, binding)
                    for role in roles
                    for binding in role.channel_bindings
                    if binding.channel == row.platform
                ]
                if not bindings:
                    continue
                if row.legacy_migrated:
                    migrated_platforms.add(row.platform)
                    continue
                candidates = tuple(sorted({role_id for role_id, _ in bindings}))
                choices = tuple(
                    LegacyOwnerRules(
                        role_id=role_id,
                        group_rules=tuple(
                            GroupResponseRule(
                                chat_id=binding.chat_id,
                                require_mention=False,
                                blocked_sender_ids=tuple(binding.blocked_senders),
                            )
                            for owner, binding in bindings
                            if owner == role_id and binding.chat_type == "group"
                        ),
                    )
                    for role_id in candidates
                )
                # Old bindings named a channel, not an account. Multiple new
                # accounts of that platform require an explicit user decision.
                unique_owner = (
                    row.role_id is None
                    and len(candidates) == len(platform_accounts) == 1
                )
                selected = next(
                    (choice for choice in choices if choice.role_id == row.role_id),
                    None,
                )
                group_rules = (
                    selected.group_rules
                    if selected is not None
                    else choices[0].group_rules if unique_owner else ()
                )
                rules = row.response_rules
                if group_rules and rules == AccountResponseRules():
                    rules = replace(
                        rules,
                        group_enabled=False,
                        group_rules=group_rules,
                    )
                updated[row.id] = replace(
                    row,
                    role_id=(
                        candidates[0]
                        if unique_owner and row.role_id is None
                        else row.role_id
                    ),
                    ownership_version=row.ownership_version
                    + int(unique_owner and row.role_id is None),
                    response_rules=rules,
                    legacy_owner_candidates=(
                        () if unique_owner or row.role_id is not None else candidates
                    ),
                    legacy_owner_rules=(
                        () if unique_owner or row.role_id is not None else choices
                    ),
                    legacy_migrated=True,
                )
                migrated_platforms.add(row.platform)
            if updated != self._records:
                self._save(updated)
            if migrated_platforms and self._retire_legacy_bindings is not None:
                self._retire_legacy_bindings(migrated_platforms)

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
        """Updates this plugin generation's live state for a registered account.

        Reports for an account mid-deletion (e.g. a channel's final "offline"
        while it is being retired) are ignored rather than applied.
        """
        with self._lock:
            if account_id in self._deleting:
                return self._runtime.snapshot(
                    self._records[account_id], generation=generation
                )
            self._runtime.report(
                account_id, token, generation, connection, capabilities, error
            )
            row = self._staged_records.get(generation, {}).get(
                account_id, self._records.get(account_id)
            )
            if row is None:
                raise KeyError(account_id)
            if capabilities and row.known_capabilities != tuple(sorted(capabilities)):
                row = replace(row, known_capabilities=tuple(sorted(capabilities)))
                if generation in {
                    DIRECT_GENERATION,
                    self._runtime.published_generation,
                }:
                    self._save({**self._records, account_id: row})
                else:
                    self._staged_records.setdefault(generation, {})[account_id] = row
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
            if was_current:
                self._discard_staged(account_id, (generation,))

    def _discard_staged(self, account_id: str, generations: Iterable[str]) -> None:
        """Drops unpublished identity data for one account in those generations."""
        for generation in list(generations):
            staged = self._staged_records.get(generation)
            if staged is None:
                continue
            staged.pop(account_id, None)
            if not staged:
                del self._staged_records[generation]

    def _ensure_not_deleting(self, account_id: str) -> None:
        if account_id in self._deleting:
            raise AccountDeletingError("账号正在删除")

    def set_delete_handler(
        self,
        plugin_id: str,
        handler: AccountDeleteHandler,
        *,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Accepts one plugin generation's cleanup hook for its own accounts."""
        with self._lock:
            self._runtime.set_delete_handler(plugin_id, handler, generation)

    def clear_delete_handler(
        self,
        plugin_id: str,
        handler: AccountDeleteHandler,
        *,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Withdraws a disposed plugin instance's cleanup hook."""
        with self._lock:
            self._runtime.clear_delete_handler(plugin_id, handler, generation)

    async def delete(
        self,
        account_id: str,
        *,
        role_id: str,
        check_plugin_config: Callable[[str, dict[str, Any]], None],
        write_plugin_config: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Deletes an owned account through its plugin's deletion plan.

        Order: the plugin's plan and ``check_plugin_config`` are pure and fail
        before anything changes; ``disconnect`` stops the account without
        losing data; ``purge`` deletes plugin data; ``write_plugin_config``
        then removes a config-held credential transactionally, which swaps
        the runtime generation, so the new generation already starts without
        the purged data and cannot reconnect it; the host record goes last.

        Residual window: a failed ``purge`` leaves some private data, and a
        failed ``write_plugin_config`` leaves the host-config credential while
        private data is already gone. Either way the record is kept and every
        step is idempotent, so a retry completes deletion. Until that retry,
        a later generation may re-import a legacy credential from host config
        (QQ/QQBot migrate it on setup); the retry plans from config again, so
        it disconnects and purges that re-import too.

        While deleting, ownership and rules are frozen, registration of the
        same identity is refused, and live reports are ignored. A disabled or
        unloaded plugin cannot clean up, so deletion is refused rather than
        orphaning secrets.
        """
        async with self._delete_lock:
            with self._lock:
                row = self._records.get(account_id)
                if row is None:
                    raise AccountNotFoundError(account_id)
                if row.role_id != role_id:
                    raise PermissionError("账号不属于该角色")
                handler = self._runtime.delete_handler(row.plugin_id)
                if handler is None:
                    raise RuntimeError(
                        f"插件 {row.plugin_id} 未启用或未加载，无法清理账号数据；"
                        "请先启用插件再删除账号"
                    )
                self._deleting.add(row.id)
            try:
                plan = handler(row.config_ref)
                if plan.plugin_config is not None:
                    check_plugin_config(row.plugin_id, plan.plugin_config)
                await plan.disconnect()
                await plan.purge()
                if plan.plugin_config is not None:
                    await write_plugin_config(row.plugin_id, plan.plugin_config)
                with self._lock:
                    self._save(
                        {
                            key: item
                            for key, item in self._records.items()
                            if key != row.id
                        }
                    )
                    self._runtime.forget(row.id)
                    self._discard_staged(row.id, self._staged_records.keys())
            finally:
                with self._lock:
                    self._deleting.discard(row.id)

    def set_response_rules(
        self, account_id: str, rules: AccountResponseRules
    ) -> AccountSnapshot:
        """Persists shared response policy without changing ownership or live state."""
        with self._lock:
            self._ensure_not_deleting(account_id)
            row = self._records[account_id]
            if row.response_rules != rules:
                row = replace(row, response_rules=rules)
                self._save({**self._records, account_id: row})
            return self._runtime.snapshot(row)

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
