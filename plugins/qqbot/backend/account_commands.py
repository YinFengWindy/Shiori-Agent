"""Explicit QQBot account settings and C2C capability RPCs."""

from __future__ import annotations

from typing import Any

import httpx

from .accounts import resolve_secret
from .channel import QQBotChannel


class _AccountCommandsMixin:
    """Expose plugin-owned account commands without coupling host settings UI."""

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
        account_id = self._register(row)
        old = self._channels.pop(app_id, None)
        if old is not None:
            await old.stop()
        try:
            await self._connect(row)
        except Exception:
            if previous is not None and previous.get("connected", True):
                await self._connect(previous)
            raise
        self._store.save(row)
        self._status(app_id, "connecting", "", "")
        return {"account_id": account_id}

    async def disconnect(self, payload: dict[str, Any]) -> dict[str, Any]:
        app_id = self._app_for_account(payload)
        row = self._store.get(app_id)
        channel = self._channels.pop(app_id, None)
        if channel is not None:
            await channel.stop()
        self._store.save({**row, "connected": False})
        self._status(app_id, "offline", "", "")
        return {"account_id": self._account_ids[app_id]}

    def _app_for_account(self, payload: dict[str, Any]) -> str:
        account_id = str(payload.get("account_id") or "")
        return next(
            app_id
            for app_id, registered in self._account_ids.items()
            if registered == account_id
        )

    async def detail(self, payload: dict[str, Any]) -> dict[str, Any]:
        app_id = self._app_for_account(payload)
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
        app_id = self._app_for_account(payload)
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

    async def send_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        app_id = self._app_for_account(payload)
        channel = self._channels.get(app_id)
        if channel is None:
            raise RuntimeError("QQBot 应用账号未连接")
        openid = str(payload.get("user_openid") or "").strip()
        if not openid or ":" in openid:
            raise ValueError("无效的 QQBot 用户 OpenID")
        content = str(payload.get("content") or "").strip()
        if not content:
            raise ValueError("发送内容不能为空")
        try:
            receipt = await channel.send(channel._chat_id(openid), content)
        except httpx.HTTPStatusError as exc:
            try:
                body = exc.response.json()
            except ValueError:
                body = {}
            reason = (
                str(body.get("message") or body.get("msg") or "").strip()
                if isinstance(body, dict)
                else ""
            )
            raise RuntimeError(
                f"QQBot 平台拒绝发送 (HTTP {exc.response.status_code})"
                + (f": {reason}" if reason else "")
            ) from exc
        if not receipt:
            raise RuntimeError("QQBot 平台未返回消息 ID，发送结果不确定")
        return {"message_id": receipt, "chat_id": channel._chat_id(openid)}
