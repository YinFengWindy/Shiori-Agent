"""Explicit QQBot account settings and C2C capability RPCs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .accounts import resolve_secret
from .channel import QQBotChannel

if TYPE_CHECKING:
    from infra.channels.contract import ChannelContext

    from .account_identity import QQBotAccountIdentity
    from .accounts import QQBotAccountStore


class _AccountCommandsMixin:
    """Account commands on a composite with identity, store, and gateway state."""

    _identity: QQBotAccountIdentity
    _store: QQBotAccountStore
    _channels: dict[str, QQBotChannel]
    _runtime: ChannelContext | None

    async def _preflight(self, app_id: str, secret: str) -> None:
        """Authenticate and query gateway before changing persisted/running creds."""
        candidate = QQBotChannel(app_id, secret)
        try:
            token = await candidate._get_access_token()
            gateway = await candidate._api_request("GET", "/gateway", token=token)
            if not str(gateway.get("url") or "").strip():
                raise RuntimeError("QQBot 网关响应缺少地址")
        finally:
            await candidate._client.aclose()

    async def save_and_connect(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply an explicit credential commit after authentication succeeds."""
        app_id = str(payload.get("app_id") or "").strip()
        if not app_id or ":" in app_id:
            raise ValueError("QQBot App ID 不能为空或包含冒号")
        previous = next(
            (row for row in self._store.list() if row["app_id"] == app_id), None
        )
        supplied = str(payload.get("client_secret") or "").strip()
        secret = supplied or (previous["client_secret"] if previous else "")
        if not secret:
            raise ValueError("QQBot App Secret 不能为空")
        resolved = resolve_secret(secret)
        if not resolved:
            raise ValueError("QQBot App Secret 环境变量未设置")
        await self._preflight(app_id, resolved)
        row = {
            "app_id": app_id,
            "client_secret": secret,
            "legacy": previous.get("legacy", False) if previous else False,
            "connected": True,
            "targets": previous.get("targets", []) if previous else [],
            "bot_id": previous.get("bot_id", "") if previous else "",
            "bot_name": previous.get("bot_name", "") if previous else "",
        }
        if previous is not None:
            self._identity.register(row)
        self._identity.begin_handoff(app_id)
        old = self._channels.pop(app_id, None)
        old_stopped = False
        try:
            if old is not None:
                await old.stop()
                old_stopped = True
            candidate = await self._connect(row)
            if self._runtime is not None and candidate is not None:
                await candidate.wait_ready()
            name, bot_id = self._identity.pending_identity(app_id)
            if name or bot_id:
                row = {**row, "bot_name": name, "bot_id": bot_id}
            account_id = self._identity.register(row)
            self._store.save(row)
        except Exception:
            failed = self._channels.pop(app_id, None)
            if failed is not None:
                await failed.stop()
            self._identity.end_handoff(app_id)
            if old is not None and not old_stopped:
                self._channels[app_id] = old
            elif previous is not None and previous.get("connected", True):
                await self._connect(previous)
            raise
        self._identity.end_handoff(app_id)
        if candidate is not None:
            candidate._account_id = account_id
        self._identity.report(
            app_id, "online" if self._runtime is not None else "connecting", "", ""
        )
        return {"account_id": account_id}

    async def disconnect(self, payload: dict[str, Any]) -> dict[str, Any]:
        app_id = self._identity.app_for_account(payload)
        row = self._store.get(app_id)
        channel = self._channels.pop(app_id, None)
        if channel is not None:
            await channel.stop()
        self._store.save({**row, "connected": False})
        self._identity.report(app_id, "offline", "", "")
        return {"account_id": self._identity.account_id(app_id)}

    async def detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        app_id = self._identity.app_for_account(payload)
        row = self._store.get(app_id)
        return {
            "app_id": app_id,
            "has_secret": bool(row["client_secret"]),
            "secret_reference": (
                row["client_secret"] if row["client_secret"].startswith("${") else ""
            ),
            "connected": row.get("connected", True),
            "identity": "QQ 官方机器人应用",
            "bot_id": row.get("bot_id", ""),
            "bot_name": row.get("bot_name", ""),
        }

    async def targets(self, payload: dict[str, Any]) -> dict[str, Any]:
        if str(payload.get("kind") or "known") != "known":
            raise ValueError("QQBot 仅支持已交互的私聊目标")
        app_id = self._identity.app_for_account(payload)
        row = self._store.get(app_id)
        return {
            "coverage": "observed_c2c_only",
            "targets": [
                {
                    "chat_id": (
                        f"c2c:{app_id}:{openid}"
                        if not row.get("legacy")
                        else f"c2c:{openid}"
                    ),
                    "user_openid": openid,
                }
                for openid in row.get("targets", [])
            ],
        }
