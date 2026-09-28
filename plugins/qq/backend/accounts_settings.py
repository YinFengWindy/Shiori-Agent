"""Managed QQ login setup and verified-account projections."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from core.accounts import AccountResponseRules
from infra.channels.intake import ChannelIntake

from .accounts_store import (
    QQAccountsStore,
    QQConnectionConfig,
)
from .napcat_installer import managed_available
from .onebot import OneBotSocket


def ensure_config_owner(config: QQConnectionConfig, role_id: str) -> None:
    """Refuses to act on a QQ configuration for any role but its owner."""
    if config.role_id != role_id:
        raise ValueError(
            "该 QQ 配置已属于另一个角色" if config.role_id else "该 QQ 配置没有所属角色"
        )


class QQAccountSettings:
    """Starts temporary managed logins without persisting an account."""

    _store: QQAccountsStore
    _configs: dict[str, QQConnectionConfig]
    _states: dict[str, tuple[str, str]]
    _ids: dict[str, str]
    _sockets: dict[str, OneBotSocket]
    _tasks: dict[str, asyncio.Task[None]]
    _locks: dict[str, asyncio.Lock]
    _intakes: dict[str, ChannelIntake]
    _avatar_tasks: dict[str, asyncio.Task[None]]
    _accounts: Any

    def _ref_for(self, account_id: str) -> str:
        """The owning runtime resolves a host account to its private config."""
        raise NotImplementedError

    def settings(self, account_id: str | None = None) -> dict[str, Any]:
        """Returns availability or one verified account without socket secrets."""
        if account_id is None:
            return {"managed_available": managed_available()}
        selected = self._ref_for(account_id)
        return {
            "account": self._public_config(selected, self._configs[selected]),
            "managed_available": managed_available(),
        }

    def _public_config(self, ref: str, config: QQConnectionConfig) -> dict[str, Any]:
        connection, error = self._states.get(ref, ("offline", ""))
        return {**config.public_dict(), "connection": connection, "error": error}

    async def begin_login(self, payload: dict[str, Any]) -> dict[str, str]:
        """Allocates one temporary NapCat instance without saving an account."""
        role_id = str(payload.get("role_id") or "").strip()
        if not managed_available():
            raise RuntimeError("托管 NapCat 仅支持 Windows x64")
        ref = self._store.new_ref()
        self._accounts.check_owner(config_ref=ref, role_id=role_id)
        uri, token = self._managed.endpoint(ref)
        config = QQConnectionConfig(
            ref,
            uri,
            token,
            auto_connect=False,
            role_id=role_id,
        )
        self._configs[ref] = config
        self._states[ref] = ("offline", "")
        return {"ref": ref}

    async def _discard_config(self, ref: str) -> None:
        """Forgets a reference's saved settings, live state, intake, and lock."""
        if ref in self._configs:
            if self._store.path.exists():
                self._store.save(
                    {key: row for key, row in self._configs.items() if key != ref}
                )
            del self._configs[ref]
        self._states.pop(ref, None)
        intake = self._intakes.pop(ref, None)
        if intake is not None:
            await intake.close()
        self._locks.pop(ref, None)

    async def _cancel_avatar(self, ref: str) -> None:
        """Stops an account's background avatar fetch before it goes away."""
        task = self._avatar_tasks.pop(ref, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def disconnect_account(self, ref: str) -> None:
        """Stops a deleted account's socket and NapCat, keeping its saved data.

        Idempotent; the host account is forgotten first so teardown never
        reports it again.
        """
        self._ids.pop(ref, None)
        await self._cancel_avatar(ref)
        task = self._tasks.pop(ref, None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with self._locks.setdefault(ref, asyncio.Lock()):
            socket = self._sockets.pop(ref, None)
            if socket is not None:
                await socket.close()
            await self._managed.stop(ref)
            if ref in self._configs:
                self._states[ref] = ("offline", "")

    def save_rules(self, ref: str, rules: AccountResponseRules) -> None:
        """Persists host-edited response rules with the account's private config."""
        config = replace(self._configs[ref], response_rules=rules)
        self._store.save({**self._configs, ref: config})
        self._configs[ref] = config

    async def prune_orphans(self) -> None:
        """Deletes unverified leftovers and accounts whose owner role is gone.

        Role deletion only reaches a loaded plugin, so accounts of a role
        deleted meanwhile are removed with all their data on the next load.
        Valid saved accounts without an owner remain for manual correction.
        """
        for ref, config in list(self._configs.items()):
            if not config.verified or (
                config.role_id and not self._accounts.role_exists(config.role_id)
            ):
                await self.purge_account(ref)

    async def purge_account(self, ref: str) -> None:
        """Deletes the account's credentials and NapCat data; idempotent."""
        # The managed instance keeps its own login session files.
        await self._managed.delete(ref)
        await self._discard_config(ref)
