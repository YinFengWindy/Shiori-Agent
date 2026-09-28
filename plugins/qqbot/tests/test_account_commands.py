from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest

import plugins.qqbot.backend.gateway as gateway_module
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
        self.roles = {}

    def register(
        self, *, platform, platform_account_id, config_ref, role_id, display_name=None
    ):
        self.roles[platform_account_id] = role_id
        assert platform == "qqbot"
        assert config_ref == f"app:{platform_account_id}"
        return SimpleNamespace(record=_AccountRecord(platform_account_id))

    def check_owner(self, *, config_ref, role_id, **_identity):
        if not role_id:
            raise ValueError("账号没有所属角色")

    def register_configured(self, **fields):
        # The host refuses an entry without an owner; the plugin must skip it.
        return self.register(**fields) if fields.get("role_id") else None

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
    with pytest.raises(ValueError, match="所属角色"):
        await manager.save_and_connect({"app_id": "100", "client_secret": "s"})
    for app_id, role_id in (("100", "mira"), ("200", "other")):
        assert await manager.save_and_connect(
            {"role_id": role_id, "app_id": app_id, "client_secret": f"secret-{app_id}"}
        ) == {"account_id": app_id}
        store.observe(app_id, "same-openid")
    # Each application is registered for, and stored with, the role saving it.
    assert accounts.roles == {"100": "mira", "200": "other"}
    assert [row["role_id"] for row in store.list()] == ["mira", "other"]
    with pytest.raises(ValueError, match="另一个角色"):
        await manager.save_and_connect(
            {"role_id": "mira", "app_id": "200", "client_secret": "secret-200"}
        )

    assert (await manager.targets({"account_id": "100"}))["targets"] == [
        {"chat_id": "c2c:100:same-openid", "user_openid": "same-openid"}
    ]
    assert (await manager.targets({"account_id": "200"}))["targets"] == [
        {"chat_id": "c2c:200:same-openid", "user_openid": "same-openid"}
    ]
    with pytest.raises(ValueError, match="私聊"):
        await manager.targets({"account_id": "100", "kind": "groups"})


@pytest.mark.asyncio
async def test_failed_credential_preflight_preserves_running_account(
    tmp_path, monkeypatch
):
    manager, store, _ = _manager(tmp_path)

    async def valid(app_id, secret):
        pass

    monkeypatch.setattr(manager, "_preflight", valid)
    await manager.save_and_connect(
        {"role_id": "mira", "app_id": "100", "client_secret": "working"}
    )
    active = manager._channels["100"]

    async def rejected(app_id, secret):
        raise ValueError("invalid secret")

    monkeypatch.setattr(manager, "_preflight", rejected)
    with pytest.raises(ValueError, match="invalid secret"):
        await manager.save_and_connect(
            {"role_id": "mira", "app_id": "100", "client_secret": "broken"}
        )
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
    await manager.save_and_connect(
        {"role_id": "mira", "app_id": "100", "client_secret": "working"}
    )
    manager._runtime = SimpleNamespace()

    with pytest.raises(RuntimeError, match="gateway rejected"):
        await manager.save_and_connect(
            {"role_id": "mira", "app_id": "100", "client_secret": "broken"}
        )

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
        await manager.save_and_connect(
            {"role_id": "mira", "app_id": "100", "client_secret": "broken"}
        )

    assert store.list() == []
    assert manager._identity.account_id("100") == ""
    assert manager._channels == {}


@pytest.mark.asyncio
async def test_credential_preflight_opens_and_closes_its_own_http_client(
    tmp_path, monkeypatch
):
    manager, _, _ = _manager(tmp_path)
    real_client = httpx.AsyncClient
    clients: list[httpx.AsyncClient] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 60})
        assert request.url.path == "/gateway"
        return httpx.Response(200, json={"url": "wss://gateway"})

    def client_factory(**kwargs) -> httpx.AsyncClient:
        client = real_client(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(gateway_module.httpx, "AsyncClient", client_factory)

    await manager._preflight("100", "secret")

    assert len(clients) == 1
    assert clients[0].is_closed


@pytest.mark.asyncio
async def test_deleted_application_closes_gateway_and_forgets_credentials(
    tmp_path,
):
    manager, store, accounts = _manager(tmp_path)
    for app_id in ("100", "200"):
        store.save(
            {
                "app_id": app_id,
                "client_secret": f"secret-{app_id}",
                "role_id": "mira",
                "targets": ["o"],
            }
        )
        manager._identity.register(store.get(app_id))
    stopped: list[str] = []

    class _Gateway:
        async def stop(self):
            stopped.append("100")
            # Shutdown may still report while the host record exists.
            manager._identity.report("100", "offline", "", "")

    manager._channels["100"] = _Gateway()

    await manager.disconnect_account("100")

    assert stopped == ["100"]
    assert "100" not in manager._channels
    assert [row["app_id"] for row in store.list()] == ["100", "200"]
    await manager.purge_account("100")
    assert [row["app_id"] for row in store.list()] == ["200"]
    assert "secret-100" not in (tmp_path / "qqbot.json").read_text(encoding="utf-8")
    assert manager._identity.account_id("100") == ""
    with pytest.raises(StopIteration):
        manager._identity.app_for_account({"account_id": "100"})
    await manager.disconnect_account("100")
    await manager.purge_account("100")
    assert [row["app_id"] for row in store.list()] == ["200"]
    manager._identity.report("100", "online", "", "late")
    assert [account_id for account_id, _ in accounts.reports] == ["100"]
