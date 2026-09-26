from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from agent.plugin_host.kv import PluginKVStore
from plugins.qqbot.backend.account_channel import QQBotAccountsChannel
from plugins.qqbot.backend.accounts import QQBotAccountStore
from plugins.qqbot.backend.channel import QQBotChannel


@dataclass
class _AccountRecord:
    id: str


class _Accounts:
    def __init__(self):
        self.reports = []

    def register(self, *, platform, platform_account_id, config_ref, display_name=None):
        assert platform == "qqbot"
        assert config_ref == f"app:{platform_account_id}"
        return SimpleNamespace(record=_AccountRecord(platform_account_id))

    def report(self, account_id, **kwargs):
        self.reports.append((account_id, kwargs))


def _manager(tmp_path):
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))
    accounts = _Accounts()
    manager = QQBotAccountsChannel(SimpleNamespace(accounts=accounts), store, ())
    return manager, store, accounts


@pytest.mark.asyncio
async def test_application_target_directories_are_isolated(tmp_path, monkeypatch):
    manager, store, accounts = _manager(tmp_path)

    async def preflight(app_id, secret):
        assert secret == f"secret-{app_id}"

    monkeypatch.setattr(manager, "_preflight", preflight)
    for app_id in ("100", "200"):
        assert await manager.save_and_connect(
            {"app_id": app_id, "client_secret": f"secret-{app_id}"}
        ) == {"account_id": app_id}
        store.observe(app_id, "same-openid")

    assert (await manager.targets({"account_id": "100"}))["targets"] == [
        {"chat_id": "c2c:100:same-openid", "user_openid": "same-openid"}
    ]
    assert (await manager.targets({"account_id": "200"}))["targets"] == [
        {"chat_id": "c2c:200:same-openid", "user_openid": "same-openid"}
    ]
    manager._status("100", "online", "", "Bot One")
    manager._status("200", "login_required", "认证失败", "")
    assert accounts.reports[-2][0] == "100"
    assert accounts.reports[-2][1]["capabilities"]
    assert accounts.reports[-1][0] == "200"
    assert accounts.reports[-1][1]["capabilities"] == frozenset()


@pytest.mark.asyncio
async def test_failed_credential_preflight_preserves_running_account(
    tmp_path, monkeypatch
):
    manager, store, _ = _manager(tmp_path)

    async def valid(app_id, secret):
        pass

    monkeypatch.setattr(manager, "_preflight", valid)
    await manager.save_and_connect({"app_id": "100", "client_secret": "working"})
    active = manager._channels["100"]

    async def rejected(app_id, secret):
        raise ValueError("invalid secret")

    monkeypatch.setattr(manager, "_preflight", rejected)
    with pytest.raises(ValueError, match="invalid secret"):
        await manager.save_and_connect({"app_id": "100", "client_secret": "broken"})
    assert store.get("100")["client_secret"] == "working"
    assert manager._channels["100"] is active


@pytest.mark.asyncio
async def test_gateway_handover_failure_restores_old_credentials(tmp_path, monkeypatch):
    manager, store, _ = _manager(tmp_path)

    async def valid(app_id, secret):
        pass

    async def start(self, ctx, *, public_hooks=True):
        if self._client_secret == "broken":
            self._report_status("login_required", "gateway rejected")
        else:
            self._report_status("online")

    async def stop(self):
        pass

    monkeypatch.setattr(manager, "_preflight", valid)
    monkeypatch.setattr(QQBotChannel, "start", start)
    monkeypatch.setattr(QQBotChannel, "stop", stop)
    await manager.save_and_connect({"app_id": "100", "client_secret": "working"})
    manager._runtime = SimpleNamespace()

    with pytest.raises(RuntimeError, match="gateway rejected"):
        await manager.save_and_connect({"app_id": "100", "client_secret": "broken"})

    assert store.get("100")["client_secret"] == "working"
    assert manager._channels["100"]._client_secret == "working"


@pytest.mark.asyncio
async def test_failed_new_gateway_does_not_create_an_account(tmp_path, monkeypatch):
    manager, store, _ = _manager(tmp_path)

    async def valid(app_id, secret):
        pass

    async def start(self, ctx, *, public_hooks=True):
        self._report_status("login_required", "gateway rejected")

    async def stop(self):
        pass

    monkeypatch.setattr(manager, "_preflight", valid)
    monkeypatch.setattr(QQBotChannel, "start", start)
    monkeypatch.setattr(QQBotChannel, "stop", stop)
    manager._runtime = SimpleNamespace()

    with pytest.raises(RuntimeError, match="gateway rejected"):
        await manager.save_and_connect({"app_id": "100", "client_secret": "broken"})

    assert store.list() == []
    assert manager._account_ids == {}
    assert manager._channels == {}


@pytest.mark.asyncio
async def test_disconnected_scoped_target_never_falls_back_to_legacy(
    tmp_path, monkeypatch
):
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))
    store.migrate_legacy("100", "secret")
    manager = QQBotAccountsChannel(SimpleNamespace(accounts=_Accounts()), store, ())

    async def valid(app_id, secret):
        pass

    monkeypatch.setattr(manager, "_preflight", valid)
    await manager.save_and_connect({"app_id": "200", "client_secret": "other"})
    await manager.disconnect({"account_id": "200"})
    with pytest.raises(RuntimeError, match="未连接"):
        await manager.send("c2c:200:user", "wrong app")
