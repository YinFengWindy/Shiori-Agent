from __future__ import annotations

import asyncio
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.qq.backend.accounts_runtime import QQAccountsRuntime
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig
from infra.persistence.json_store import atomic_save_json


class _Accounts:
    def __init__(self) -> None:
        self.rows: dict[str, SimpleNamespace] = {}
        self.states: dict[str, str] = {}
        self.reports: list[tuple[str, str, str]] = []

    def register(
        self,
        *,
        platform,
        platform_account_id,
        config_ref,
        role_id,
        display_name=None,
        response_rules=None,
    ):
        account_id = f"qq-{platform_account_id}"
        row = SimpleNamespace(id=account_id, config_ref=config_ref, role_id=role_id)
        self.rows[account_id] = row
        return SimpleNamespace(record=row)

    def check_owner(self, *, config_ref, role_id, **_identity):
        if not role_id:
            raise ValueError("账号没有所属角色")

    def role_exists(self, role_id):
        return True

    def register_saved(self, **fields):
        return self.register(**fields) if fields.get("role_id") else None

    def report(self, account_id, *, connection, capabilities=frozenset(), error=""):
        self.states[account_id] = connection
        self.reports.append((account_id, connection, error))
        return SimpleNamespace(record=self.rows[account_id])


class _Socket:
    def __init__(self, identity: str) -> None:
        self.identity = identity
        self.closed = False
        self.waiting = asyncio.Event()
        self.calls: list[tuple[str, dict]] = []

    async def call(self, action, params=None):
        self.calls.append((action, params or {}))
        if action == "get_login_info":
            return {"user_id": int(self.identity), "nickname": "bot"}
        if action == "get_status":
            return {"online": True}
        raise AssertionError(action)

    async def wait_closed(self):
        await self.waiting.wait()

    async def close(self):
        self.closed = True
        self.waiting.set()


@pytest.mark.asyncio
async def test_managed_qr_wait_is_normal_and_does_not_register_fake_identity(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    accounts = _Accounts()
    runtime = QQAccountsRuntime(QQAccountsStore(tmp_path), accounts)
    start = AsyncMock()
    status = AsyncMock(
        return_value={
            "phase": "login_required",
            "login_phase": "waiting_qrcode",
            "qrcode": "data:image/png;base64,QR",
            "error": "",
        }
    )
    monkeypatch.setattr(runtime._managed, "start", start)
    monkeypatch.setattr(runtime._managed, "login_status", status)
    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]

    assert await runtime.start_login(ref) == {"ref": ref, "account_id": ""}
    for _ in range(50):
        if runtime._states.get(ref, ("", ""))[0] == "login_required":
            break
        await asyncio.sleep(0.01)
    assert runtime._states[ref] == ("login_required", "")
    assert accounts.rows == {}
    assert not runtime._store.path.exists()
    assert (await runtime.managed_status(ref))["login"]["qrcode"].startswith(
        "data:image"
    )
    start.assert_awaited_once_with(ref, "")

    stop = AsyncMock()
    monkeypatch.setattr(runtime._managed, "stop", stop)
    await runtime.stop_login(ref)
    stop.assert_awaited_once_with(ref)
    assert runtime._configs[ref].auto_connect is False
    await runtime.cancel_login(ref)
    assert ref not in runtime._configs
    assert not runtime._managed._files.account_dir(ref).exists()
    await runtime.stop()


@pytest.mark.asyncio
async def test_managed_scan_registers_only_after_verified_onebot_identity(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    store = QQAccountsStore(tmp_path)
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    start = AsyncMock()
    login_status = AsyncMock(
        side_effect=[
            {
                "phase": "login_required",
                "qrcode": "data:image/png;base64,QR",
                "error": "",
            },
            {"phase": "online", "qrcode": "", "error": ""},
        ]
    )
    socket = _Socket("101")
    socket.open = AsyncMock()
    monkeypatch.setattr(runtime._managed, "start", start)
    monkeypatch.setattr(runtime._managed, "login_status", login_status)
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.OneBotSocket", lambda *_args: socket
    )
    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]

    assert (await runtime.start_login(ref))["account_id"] == ""
    for _ in range(50):
        if runtime._states.get(ref, ("", ""))[0] == "login_required":
            break
        await asyncio.sleep(0.01)
    assert accounts.rows == {}
    socket.open.assert_not_awaited()
    for _ in range(150):
        if accounts.states.get("qq-101") == "online":
            break
        await asyncio.sleep(0.02)

    assert login_status.await_count == 2
    socket.open.assert_awaited_once()
    assert socket.calls[:2] == [("get_login_info", {}), ("get_status", {})]
    assert accounts.states["qq-101"] == "online"
    assert accounts.rows["qq-101"].config_ref == ref
    assert store.load()[ref].expected_uin == "101"
    assert store.load()[ref].verified is True
    login_status.side_effect = None
    login_status.return_value = {"phase": "online", "qrcode": "", "error": ""}
    assert (await runtime.managed_status(ref))["account_id"] == "qq-101"
    await runtime.cancel_login(ref)
    assert store.load()[ref].expected_uin == "101"
    await runtime.stop()


@pytest.mark.asyncio
async def test_existing_managed_session_connects_without_qr(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    store = QQAccountsStore(tmp_path)
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    start = AsyncMock()
    login_status = AsyncMock(
        return_value={"phase": "online", "qrcode": "", "error": ""}
    )
    socket = _Socket("101")
    socket.open = AsyncMock()
    monkeypatch.setattr(runtime._managed, "start", start)
    monkeypatch.setattr(runtime._managed, "login_status", login_status)
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_runtime.OneBotSocket", lambda *_args: socket
    )
    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]

    await runtime.start_login(ref)
    for _ in range(50):
        if accounts.states.get("qq-101") == "online":
            break
        await asyncio.sleep(0.01)
    assert accounts.states["qq-101"] == "online"
    assert login_status.await_count == 1
    assert store.load()[ref].verified is True
    assert (await runtime.managed_status(ref))["login"]["qrcode"] == ""
    await runtime.stop()


@pytest.mark.asyncio
async def test_restart_removes_unverified_record_and_orphan_instance(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    abandoned = QQConnectionConfig(
        "aabb", "ws://127.0.0.1:3001", "token", role_id="mira"
    )
    atomic_save_json(store.path, {"version": 1, "accounts": [asdict(abandoned)]})
    runtime = QQAccountsRuntime(store, _Accounts())
    orphan = runtime._managed._files.account_dir("ccdd")
    orphan.mkdir(parents=True)
    saved_temp = runtime._managed._files.account_dir("aabb")
    saved_temp.mkdir(parents=True)

    await runtime.load()
    assert store.load() == {}
    assert not saved_temp.exists()
    assert not orphan.exists()


@pytest.mark.asyncio
async def test_managed_logout_keeps_identity_but_clears_login(monkeypatch, tmp_path):
    store = QQAccountsStore(tmp_path)
    config = QQConnectionConfig(
        "known",
        "ws://127.0.0.1:3001",
        "secret",
        expected_uin="101",
        verified=True,
        role_id="mira",
    )
    store.save({"known": config})
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    runtime.register_saved()
    stop = AsyncMock()
    logout = AsyncMock()
    monkeypatch.setattr(runtime._managed, "stop", stop)
    monkeypatch.setattr(runtime._managed, "logout", logout)

    await runtime.logout("qq-101")
    stop.assert_awaited_once_with("known")
    logout.assert_awaited_once_with("known")
    assert store.load()["known"].expected_uin == "101"
    assert store.load()["known"].auto_connect is False
    assert accounts.states["qq-101"] == "login_required"
