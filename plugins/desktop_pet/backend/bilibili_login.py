"""Per-role Bilibili QR login flow, account status and credential access.

The login is only used to receive full viewer identities on the danmaku
connection; nothing here sends anything to Bilibili beyond login and nav reads.
"""

from __future__ import annotations

import base64
import io
from typing import Literal

import qrcode
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.roles import Roles

from .bilibili_api import BilibiliLoginApi, QrScanState
from .bilibili_credentials import BilibiliCredentialStore, BilibiliCredentials

AccountState = Literal["logged_out", "logged_in", "invalid"]


class BilibiliLoginRequired(RuntimeError):
    """The role has no Bilibili login, or its stored login is no longer valid."""


class BilibiliLoginService:
    """Owns pending QR keys (in memory) and stored credentials (on disk)."""

    def __init__(
        self, roles: Roles, store: BilibiliCredentialStore, api: BilibiliLoginApi
    ) -> None:
        self._roles = roles
        self._store = store
        self._api = api
        # role id -> qrcode_key being polled; one in-flight QR per role.
        self._pending: dict[str, str] = {}

    async def start(self, role_id: str) -> dict[str, object]:
        """Issue a fresh QR for the role, replacing any earlier pending one."""
        self._require_role(role_id)
        ticket = await self._api.generate_qrcode()
        self._pending[role_id] = ticket.key
        return {"state": QrScanState.WAITING_SCAN.value, "qrcode": _qr_png(ticket.url)}

    async def poll(self, role_id: str) -> dict[str, object]:
        """Advance the role's pending QR; a confirmed scan persists credentials."""
        self._require_role(role_id)
        key = self._pending.get(role_id)
        if key is None:
            raise ValueError("没有进行中的 B 站扫码登录")
        result = await self._api.poll_qrcode(key)
        # Logout or a newer QR during the request supersedes this answer.
        if self._pending.get(role_id) != key:
            raise ValueError("该 B 站扫码登录已被取消")
        if result.state is QrScanState.EXPIRED:
            del self._pending[role_id]
        if result.state is not QrScanState.SUCCESS:
            return {"state": result.state.value}
        account = await self._api.fetch_account(result.cookies)
        if account is None:
            raise BilibiliLoginRequired("B 站扫码成功但登录态校验未通过")
        if self._pending.get(role_id) != key:
            raise ValueError("该 B 站扫码登录已被取消")
        del self._pending[role_id]
        self._store.write(
            role_id,
            BilibiliCredentials(
                uid=account.uid,
                uname=account.uname,
                cookies=result.cookies,
                refresh_token=result.refresh_token,
            ),
        )
        return {
            "state": result.state.value,
            "account": _account(account.uid, account.uname),
        }

    async def status(self, role_id: str) -> dict[str, object]:
        """Report logged_out / logged_in (with nickname) / invalid, checked live."""
        self._require_role(role_id)
        credentials = self._store.read(role_id)
        if credentials is None:
            return {"state": "logged_out"}
        account = await self._api.fetch_account(credentials.cookies)
        if account is None:
            return {
                "state": "invalid",
                "account": _account(credentials.uid, credentials.uname),
            }
        return {"state": "logged_in", "account": _account(account.uid, account.uname)}

    def logout(self, role_id: str) -> dict[str, object]:
        """Drop stored credentials and any pending QR for the role."""
        self._require_role(role_id)
        self._pending.pop(role_id, None)
        self._store.delete(role_id)
        return {"state": "logged_out"}

    async def require_credentials(self, role_id: str) -> BilibiliCredentials:
        """Credentials for the live engine; never degrades to anonymous access.

        Raises ``BilibiliLoginRequired`` when the role is not logged in or the
        stored login was rejected by Bilibili.
        """
        credentials = self._store.read(role_id)
        if credentials is None:
            raise BilibiliLoginRequired("桌宠角色尚未登录 B 站")
        if await self._api.fetch_account(credentials.cookies) is None:
            raise BilibiliLoginRequired("B 站登录已失效，请重新扫码")
        return credentials

    def prune_deleted_roles(self) -> None:
        """Remove credentials and pending QRs of roles that no longer exist."""
        role_ids = {role.id for role in self._roles.list_roles()}
        for role_id in [key for key in self._pending if key not in role_ids]:
            del self._pending[role_id]
        self._store.prune(role_ids)

    async def on_role_deleted(self, event: RoleDeleted) -> None:
        """A deleted role's login must not outlive it."""
        self._pending.pop(event.role_id, None)
        self._store.delete(event.role_id)

    def _require_role(self, role_id: str) -> None:
        if not role_id or self._roles.get_role(role_id) is None:
            raise ValueError("桌宠角色不存在")


def _account(uid: int, uname: str) -> dict[str, object]:
    return {"uid": uid, "uname": uname}


def _qr_png(content: str) -> str:
    """Encode the login URL as a PNG data URI the UI can show directly."""
    buffer = io.BytesIO()
    qrcode.make(content).save(buffer)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
