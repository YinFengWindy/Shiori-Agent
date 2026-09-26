from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
import httpx

from agent.plugin_host.kv import PluginKVStore
from plugins.qqbot.backend.account_channel import QQBotAccountsChannel
from plugins.qqbot.backend.accounts import QQBotAccountStore


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
async def test_application_targets_and_send_receipts_are_isolated(
    tmp_path, monkeypatch
):
    manager, store, accounts = _manager(tmp_path)

    async def preflight(app_id, secret):
        assert secret == f"secret-{app_id}"

    monkeypatch.setattr(manager, "_preflight", preflight)
    for app_id in ("100", "200"):
        assert await manager.save_and_connect(
            {"app_id": app_id, "client_secret": f"secret-{app_id}"}
        ) == {"account_id": app_id}
        store.observe(app_id, "same-openid")

    for app_id in ("100", "200"):
        channel = manager._channels[app_id]

        async def token():
            return "token"

        async def request(method, path, body=None, token=None, *, identity=app_id):
            assert path == "/v2/users/same-openid/messages"
            assert method == "POST"
            return {"id": f"message-{identity}"}

        monkeypatch.setattr(channel, "_get_access_token", token)
        monkeypatch.setattr(channel, "_api_request", request)

    assert (await manager.targets({"account_id": "100"}))["targets"] == [
        {"chat_id": "c2c:100:same-openid", "user_openid": "same-openid"}
    ]
    assert (await manager.targets({"account_id": "200"}))["targets"] == [
        {"chat_id": "c2c:200:same-openid", "user_openid": "same-openid"}
    ]
    assert await manager.send_target(
        {"account_id": "200", "user_openid": "same-openid", "content": "hi"}
    ) == {"message_id": "message-200", "chat_id": "c2c:200:same-openid"}
    with pytest.raises(ValueError, match="不属于此应用"):
        await manager._channels["100"].send("c2c:200:same-openid", "wrong")
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
async def test_send_reports_platform_failure_reason(tmp_path, monkeypatch):
    manager, _, _ = _manager(tmp_path)

    async def valid(app_id, secret):
        pass

    monkeypatch.setattr(manager, "_preflight", valid)
    await manager.save_and_connect({"app_id": "100", "client_secret": "secret"})
    channel = manager._channels["100"]
    request = httpx.Request(
        "POST", "https://api.sgroup.qq.com/v2/users/opaque/messages"
    )
    response = httpx.Response(
        403, json={"message": "target unavailable"}, request=request
    )

    async def denied(chat_id, content):
        raise httpx.HTTPStatusError("rejected", request=request, response=response)

    monkeypatch.setattr(channel, "send", denied)
    with pytest.raises(RuntimeError, match="HTTP 403.*target unavailable"):
        await manager.send_target(
            {"account_id": "100", "user_openid": "opaque", "content": "hello"}
        )


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
