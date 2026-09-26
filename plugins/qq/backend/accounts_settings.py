"""Plugin-private QQ connection drafts and safe settings projections."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from math import isfinite
from typing import Any
from urllib.parse import urlsplit

from infra.channels.intake import ChannelIntake

from .accounts_store import QQAccountsStore, QQConnectionConfig, QQPendingConnection
from .onebot import OneBotSocket


def validate_endpoint(uri: str) -> str:
    """Accepts only a concrete NapCat forward WebSocket address."""
    parsed = urlsplit(uri)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise ValueError("NapCat 地址必须是 ws:// 或 wss:// WebSocket 地址")
    return uri


class QQAccountSettings:
    """Stores pending edits without replacing a verified active connection."""

    _store: QQAccountsStore
    _configs: dict[str, QQConnectionConfig]
    _states: dict[str, tuple[str, str]]
    _ids: dict[str, str]
    _sockets: dict[str, OneBotSocket]
    _tasks: dict[str, asyncio.Task[None]]
    _locks: dict[str, asyncio.Lock]
    _intakes: dict[str, ChannelIntake]
    _accounts: Any

    def _ref_for(self, account_id: str) -> str:
        """The owning runtime resolves a host account to its private config."""
        raise NotImplementedError

    def settings(
        self, account_id: str | None = None, ref: str | None = None
    ) -> dict[str, Any]:
        """Returns safe editable fields without returning an access token."""
        if account_id is None and ref is None:
            return {
                "accounts": [
                    self._public_config(key, row) for key, row in self._configs.items()
                ]
            }
        selected = self._ref_for(account_id) if account_id else str(ref)
        return {"account": self._public_config(selected, self._configs[selected])}

    def _public_config(self, ref: str, config: QQConnectionConfig) -> dict[str, Any]:
        connection, error = self._states.get(ref, ("offline", ""))
        return {**config.public_dict(), "connection": connection, "error": error}

    async def save_draft(self, payload: dict[str, Any]) -> dict[str, str]:
        """Persists a draft without changing a verified connection or its restart."""
        account_id = str(payload.get("account_id") or "")
        supplied_ref = str(payload.get("ref") or "")
        ref = (
            self._ref_for(account_id)
            if account_id
            else supplied_ref or self._store.new_ref()
        )
        if supplied_ref and supplied_ref not in self._configs:
            raise KeyError("QQ 配置引用不存在")
        if account_id and supplied_ref and supplied_ref != ref:
            raise ValueError("QQ 账号与配置引用不匹配")
        if not account_id and supplied_ref and self._configs[ref].verified:
            raise PermissionError("已验证 QQ 账号必须按账号 ID 编辑")
        old = self._configs.get(ref)
        uri = validate_endpoint(str(payload.get("ws_uri") or "").strip())
        editable = (old.pending or old) if old else None
        token = (
            ""
            if payload.get("clear_token") is True
            else str(payload.get("ws_token") or (editable.ws_token if editable else ""))
        )
        timeout = float(payload.get("timeout_seconds", 5.0))
        if not isfinite(timeout) or timeout <= 0:
            raise ValueError("连接超时必须大于零")
        config = (
            replace(old, pending=QQPendingConnection(uri, token, timeout))
            if old is not None and old.verified
            else QQConnectionConfig(
                ref,
                uri,
                token,
                expected_uin=old.expected_uin if old else "",
                display_name=old.display_name if old else "",
                timeout_seconds=timeout,
                auto_connect=False,
            )
        )
        async with self._locks.setdefault(ref, asyncio.Lock()):
            self._store.save({**self._configs, ref: config})
            self._configs[ref] = config
            if not config.verified and ref not in self._sockets:
                task = self._tasks.pop(ref, None)
                if task is not None:
                    task.cancel()
                if ref in self._ids:
                    self._accounts.report(self._ids[ref], connection="offline")
                self._states[ref] = ("offline", "")
            return {"ref": ref}

    async def remove_draft(self, ref: str) -> None:
        """Discards only an unverified, stopped connection draft."""
        config = self._configs[ref]
        if ref == "legacy":
            raise PermissionError("旧 QQ 配置仍在宿主设置中，不能删除迁移记录")
        if config.verified or config.auto_connect or ref in self._sockets:
            raise PermissionError("已验证或运行中的 QQ 账号不能作为草稿删除")
        self._store.save({key: row for key, row in self._configs.items() if key != ref})
        del self._configs[ref]
        self._states.pop(ref, None)
        intake = self._intakes.pop(ref, None)
        if intake is not None:
            await intake.close()
        self._locks.pop(ref, None)
