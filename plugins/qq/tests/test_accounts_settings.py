from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.qq.backend.accounts_runtime import QQAccountsRuntime
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig


class _Accounts:
    def __init__(self) -> None:
        self.reports: list[tuple[str, str]] = []

    def register(
        self,
        *,
        platform,
        platform_account_id,
        config_ref,
        role_id,
        display_name,
        response_rules=None,
    ):
        return SimpleNamespace(record=SimpleNamespace(id=f"qq-{platform_account_id}"))

    def check_owner(self, *, config_ref, role_id, **_identity):
        if not role_id:
            raise ValueError("账号没有所属角色")

    def role_exists(self, role_id):
        return True

    def register_saved(self, **fields):
        return self.register(**fields) if fields.get("role_id") else None

    def report(self, account_id, *, connection, capabilities=frozenset(), error=""):
        self.reports.append((account_id, connection))


@pytest.mark.asyncio
async def test_temporary_login_uses_private_endpoint_without_persisting_an_account(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "plugins.qq.backend.accounts_settings.managed_available", lambda: True
    )
    store = QQAccountsStore(tmp_path)
    runtime = QQAccountsRuntime(store, _Accounts())
    start = AsyncMock()
    monkeypatch.setattr(runtime._managed, "start", start)

    ref = (await runtime.begin_login({"role_id": "mira"}))["ref"]
    temporary = runtime._configs[ref]
    assert temporary.ws_uri.startswith("ws://127.0.0.1:")
    assert temporary.ws_token
    assert temporary.auto_connect is False
    assert not store.path.exists()
    assert temporary.ws_token not in str(runtime.settings())
    start.assert_not_awaited()

    reopened = QQAccountsRuntime(store, _Accounts())
    await reopened.load()
    assert ref not in reopened._configs
    assert not reopened._managed._files.account_dir(ref).exists()
    await runtime.cancel_login(ref)
    assert ref not in runtime._configs
    assert not store.path.exists()


class _Socket:
    closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_deleted_managed_account_disconnects_and_purges_only_its_data(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            ref: QQConnectionConfig(
                ref,
                "ws://127.0.0.1:3001",
                f"token-{ref}",
                expected_uin=uin,
                auto_connect=False,
                verified=True,
                role_id="mira",
            )
            for ref, uin in (("aa", "101"), ("bb", "202"))
        }
    )
    accounts = _Accounts()
    runtime = QQAccountsRuntime(store, accounts)
    socket = _Socket()
    runtime._sockets["aa"] = socket
    reconnect = asyncio.create_task(asyncio.sleep(3600))
    runtime._tasks["aa"] = reconnect
    files = runtime._managed._files
    for ref in ("aa", "bb"):
        login = files.account_dir(ref) / "profile/AppData/Roaming/Tencent/QQNT"
        login.mkdir(parents=True)
        (login / "session.db").write_text("login", encoding="utf-8")

    await runtime.disconnect_account("aa")
    assert socket.closed and reconnect.cancelled()
    assert "token-aa" in store.path.read_text(encoding="utf-8")
    assert (files.account_dir("aa") / "profile").is_dir()

    await runtime.purge_account("aa")
    assert not files.account_dir("aa").exists()
    assert (files.account_dir("bb") / "profile").is_dir()
    assert list(store.load()) == ["bb"]
    assert "token-aa" not in store.path.read_text(encoding="utf-8")
    assert store.load()["bb"].expected_uin == "202"
    assert accounts.reports == []
