"""In-memory account index over the accounts loaded plugins register."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from threading import RLock
from typing import Callable

from .avatar import validate_avatar
from .models import (
    AccountAccess,
    AccountDeleteHandler,
    AccountDeletingError,
    AccountNotFoundError,
    AccountRecord,
    AccountResponseRules,
    AccountRulesHandler,
    AccountSnapshot,
    ConnectionState,
    account_id_for,
)
from .runtime_state import DIRECT_GENERATION, AccountRuntimeState

# Called with an account ID after its published snapshot changed or it was
# added or removed; must not block, since it runs on the reporting call.
AccountChangeListener = Callable[[str], None]


class AccountRegistry:
    """Indexes plugin-owned accounts per plugin generation; persists nothing.

    Each plugin saves its accounts (identity, owner role, response rules,
    credentials) itself and registers them again whenever it loads. Routing,
    authorization, sending and the UI read the published generation's index,
    so a disabled or unloaded plugin's accounts are simply absent.
    """

    def __init__(
        self, role_exists: Callable[[str], bool], *, lock: RLock | None = None
    ) -> None:
        self._role_exists = role_exists
        self._lock = lock or RLock()
        self._runtime = AccountRuntimeState()
        self._delete_lock = asyncio.Lock()
        # Accounts mid-deletion; identity and rules are frozen until it ends.
        self._deleting: set[str] = set()
        self._change_listeners: list[AccountChangeListener] = []

    def add_change_listener(self, listener: AccountChangeListener) -> None:
        """Subscribes to published account changes (added, removed, re-reported).

        Only real changes notify: a report or registration that leaves the
        published snapshot as it was does not.
        """
        self._change_listeners.append(listener)

    def remove_change_listener(self, listener: AccountChangeListener) -> None:
        """Withdraws a listener added with ``add_change_listener``."""
        self._change_listeners = [
            known for known in self._change_listeners if known != listener
        ]

    def _published_view(self, account_id: str) -> AccountSnapshot | None:
        """The published snapshot of an account, or None when it is not listed."""
        row = self._runtime.published.records.get(account_id)
        return None if row is None else self._runtime.snapshot(row)

    def _notify_if_changed(
        self, account_id: str, before: AccountSnapshot | None
    ) -> None:
        """Tells listeners when the published view of ``account_id`` changed."""
        with self._lock:
            after = self._published_view(account_id)
        if after != before:
            for listener in list(self._change_listeners):
                listener(account_id)

    def role_exists(self, role_id: str) -> bool:
        """Whether an owner role still exists, for plugins pruning orphaned accounts."""
        return self._role_exists(role_id)

    def publish_generation(self, generation: str) -> None:
        """Makes one prepared plugin generation's index authoritative."""
        with self._lock:
            self._runtime.publish(generation)

    def drop_generation(self, generation: str) -> None:
        """Discards a candidate or retired generation's index."""
        with self._lock:
            self._runtime.drop(generation)

    def list(self, *, role_id: str | None = None) -> list[AccountSnapshot]:
        """Returns loaded plugins' accounts with their current connection reports."""
        with self._lock:
            return [
                self._runtime.snapshot(row)
                for row in self._runtime.published.records.values()
                if role_id is None or row.role_id == role_id
            ]

    def get(self, account_id: str) -> AccountSnapshot:
        """Returns one loaded account and its current plugin report."""
        with self._lock:
            return self._runtime.snapshot(self._published_record(account_id))

    def _published_record(self, account_id: str) -> AccountRecord:
        row = self._runtime.published.records.get(account_id)
        if row is None:
            raise AccountNotFoundError(account_id)
        return row

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
        response_rules: AccountResponseRules | None = None,
    ) -> AccountSnapshot:
        """Indexes an owned account; omitted display fields and rules are retained.

        The ownership rule is ``_ownership_refusal``; a refused account raises
        ValueError and is not indexed, as does an ``avatar_url`` that is not
        empty or a valid image data URI (``validate_avatar``).
        """
        fields = (plugin_id, platform, platform_account_id, config_ref, token)
        if any(not isinstance(value, str) or not value.strip() for value in fields):
            raise ValueError("账号身份、配置引用和运行令牌不能为空")
        if avatar_url is not None:
            validate_avatar(avatar_url)
        plugin_id, platform, platform_account_id, config_ref, token = (
            value.strip() for value in fields
        )
        account_id = account_id_for(plugin_id, platform_account_id)
        with self._lock:
            before = self._published_view(account_id)
            records = self._runtime.generation(generation).records
            refusal = self._ownership_refusal(
                records,
                plugin_id=plugin_id,
                config_ref=config_ref,
                role_id=role_id,
                account_id=account_id,
            )
            if refusal is not None:
                raise ValueError(refusal)
            # A concurrent generation must not revive an account mid-delete.
            self._ensure_not_deleting(account_id)
            self._runtime.ensure_registration_allowed(account_id, token, generation)
            existing = records.get(account_id)
            row = (
                replace(
                    existing,
                    display_name=(
                        existing.display_name if display_name is None else display_name
                    ),
                    avatar_url=(
                        existing.avatar_url if avatar_url is None else avatar_url
                    ),
                    response_rules=(
                        existing.response_rules
                        if response_rules is None
                        else response_rules
                    ),
                )
                if existing is not None
                else AccountRecord(
                    id=account_id,
                    plugin_id=plugin_id,
                    platform=platform,
                    platform_account_id=platform_account_id,
                    config_ref=config_ref,
                    role_id=str(role_id).strip(),
                    display_name=display_name or "",
                    avatar_url=avatar_url or "",
                    response_rules=response_rules or AccountResponseRules(),
                )
            )
            self._runtime.register(row, token, generation)
            snapshot = self._runtime.snapshot(row, generation=generation)
        self._notify_if_changed(account_id, before)
        return snapshot

    def _ownership_refusal(
        self,
        records: dict[str, AccountRecord],
        *,
        plugin_id: str,
        config_ref: str,
        role_id: str | None,
        account_id: str | None,
    ) -> str | None:
        """The one ownership rule; returns why ``role_id`` may not hold this account.

        The owner must be an existing role; a platform account belongs to one
        plugin entry and one role; and a role holds at most one account per
        plugin. Without a known identity the account is found by its plugin
        configuration reference.
        """
        if not role_id or not role_id.strip():
            return "账号没有所属角色"
        role_id = role_id.strip()
        if not self._role_exists(role_id):
            return f"角色不存在：{role_id}"
        existing = (
            records.get(account_id)
            if account_id is not None
            else next(
                (
                    row
                    for row in records.values()
                    if (row.plugin_id, row.config_ref) == (plugin_id, config_ref)
                ),
                None,
            )
        )
        if existing is not None:
            if existing.config_ref != config_ref:
                return "平台账号已作为另一个账号添加"
            if existing.role_id != role_id:
                return "平台账号已属于另一个角色"
        for row in records.values():
            if row.plugin_id != plugin_id or row is existing:
                continue
            if row.config_ref == config_ref:
                return "配置引用已属于另一个账号"
            if row.role_id == role_id:
                return "该角色在这个渠道已有账号"
        return None

    def check_owner(
        self,
        *,
        plugin_id: str,
        config_ref: str,
        role_id: str | None,
        platform_account_id: str | None = None,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Raises ValueError unless ``role_id`` may hold this account.

        Plugins call it before saving account data of their own, so nothing is
        saved that registration would refuse.
        """
        with self._lock:
            refusal = self._ownership_refusal(
                self._runtime.generation(generation).records,
                plugin_id=plugin_id,
                config_ref=config_ref,
                role_id=role_id,
                account_id=(
                    account_id_for(plugin_id, platform_account_id)
                    if platform_account_id
                    else None
                ),
            )
        if refusal is not None:
            raise ValueError(refusal)

    def reject(
        self, plugin_id: str, message: str, *, generation: str = DIRECT_GENERATION
    ) -> None:
        """Records a saved account a plugin generation could not register."""
        with self._lock:
            self._runtime.generation(generation).rejected.setdefault(
                plugin_id, []
            ).append(message)

    def rejected(self, plugin_id: str) -> list[str]:
        """Saved accounts the running plugin could not register, with reasons."""
        with self._lock:
            return list(self._runtime.published.rejected.get(plugin_id, []))

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
            state = self._runtime.generation(generation)
            if account_id in self._deleting:
                return self._runtime.snapshot(
                    state.records[account_id], generation=generation
                )
            before = self._published_view(account_id)
            row = self._runtime.report(
                account_id, token, generation, connection, capabilities, error
            )
            snapshot = self._runtime.snapshot(row, generation=generation)
        self._notify_if_changed(account_id, before)
        return snapshot

    def unregister(
        self, account_id: str, token: str, *, generation: str = DIRECT_GENERATION
    ) -> None:
        """Stops one account's live presence while its plugin keeps it listed."""
        with self._lock:
            before = self._published_view(account_id)
            self._runtime.unregister(account_id, token, generation)
        self._notify_if_changed(account_id, before)

    def release(
        self, account_id: str, token: str, *, generation: str = DIRECT_GENERATION
    ) -> None:
        """Removes a disposed plugin instance's account from its generation."""
        with self._lock:
            before = self._published_view(account_id)
            self._runtime.release(account_id, token, generation)
        self._notify_if_changed(account_id, before)

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
            handlers = self._runtime.generation(generation).delete_handlers
            if plugin_id in handlers:
                raise ValueError(f"Account delete hook already registered: {plugin_id}")
            handlers[plugin_id] = handler

    def clear_delete_handler(
        self,
        plugin_id: str,
        handler: AccountDeleteHandler,
        *,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Withdraws a disposed plugin instance's cleanup hook, never a replacement's."""
        with self._lock:
            handlers = self._runtime.generation(generation).delete_handlers
            if handlers.get(plugin_id) is handler:
                del handlers[plugin_id]

    def set_rules_handler(
        self,
        plugin_id: str,
        handler: AccountRulesHandler,
        *,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Accepts one plugin generation's hook that saves response rules."""
        with self._lock:
            handlers = self._runtime.generation(generation).rules_handlers
            if plugin_id in handlers:
                raise ValueError(f"Account rules hook already registered: {plugin_id}")
            handlers[plugin_id] = handler

    def clear_rules_handler(
        self,
        plugin_id: str,
        handler: AccountRulesHandler,
        *,
        generation: str = DIRECT_GENERATION,
    ) -> None:
        """Withdraws a disposed plugin instance's rules hook, never a replacement's."""
        with self._lock:
            handlers = self._runtime.generation(generation).rules_handlers
            if handlers.get(plugin_id) is handler:
                del handlers[plugin_id]

    async def delete(self, account_id: str, *, role_id: str) -> None:
        """Deletes an owned account through its plugin, then drops it from the index.

        The plugin's plan is pure and fails before anything changes;
        ``disconnect`` stops the account without losing data, ``purge``
        deletes its record, credentials and private data; the index entry goes
        last. A failed step leaves the account listed and every step is
        idempotent, so a retry completes deletion. While deleting, rules are
        frozen, registration of the same identity is refused, and live
        reports are ignored.
        """
        async with self._delete_lock:
            with self._lock:
                row = self._published_record(account_id)
                if row.role_id != role_id:
                    raise PermissionError("账号不属于该角色")
                handler = self._runtime.published.delete_handlers.get(row.plugin_id)
                if handler is None:
                    raise RuntimeError(f"插件 {row.plugin_id} 未提供账号删除能力")
                self._deleting.add(row.id)
            try:
                plan = handler(row.config_ref)
                await plan.disconnect()
                await plan.purge()
                with self._lock:
                    before = self._published_view(row.id)
                    self._runtime.forget(row.id)
            finally:
                with self._lock:
                    self._deleting.discard(row.id)
            self._notify_if_changed(row.id, before)

    async def delete_role_accounts(self, role_id: str) -> list[str]:
        """Deletes every account a loaded plugin holds for ``role_id``.

        Stops at the first failure so the role is kept and deletion can be
        retried; accounts of plugins that are not loaded are removed by their
        plugin when it next loads and finds the role gone.
        """
        deleted: list[str] = []
        for snapshot in self.list(role_id=role_id):
            await self.delete(snapshot.record.id, role_id=role_id)
            deleted.append(snapshot.record.id)
        return deleted

    def set_response_rules(
        self, account_id: str, rules: AccountResponseRules
    ) -> AccountSnapshot:
        """Has the owning plugin save new rules, then applies them to the index."""
        with self._lock:
            self._ensure_not_deleting(account_id)
            row = self._published_record(account_id)
            handler = self._runtime.published.rules_handlers.get(row.plugin_id)
            if handler is None:
                raise RuntimeError(f"插件 {row.plugin_id} 未提供响应规则保存能力")
            if row.response_rules != rules:
                handler(row.config_ref, rules)
                # Every generation holding the account sees the saved rules.
                for state in self._runtime.generations():
                    current = state.records.get(account_id)
                    if current is not None:
                        state.records[account_id] = replace(
                            current, response_rules=rules
                        )
            return self._runtime.snapshot(self._published_record(account_id))

    def authorize(self, account_id: str, role_id: str) -> AccountAccess:
        """Captures an online, owned account for a later operation."""
        with self._lock:
            return self._runtime.authorize(self._published_record(account_id), role_id)

    def validate_access(self, access: AccountAccess) -> bool:
        """Rejects an in-flight operation after deletion or plugin handover."""
        with self._lock:
            return self._runtime.validate_access(access)
