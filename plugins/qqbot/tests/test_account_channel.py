from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agent.plugin_host.kv import PluginKVStore
from bus.event_bus import EventBus
from plugins.qqbot.backend.account_channel import QQBotAccountsChannel
from plugins.qqbot.backend.accounts import QQBotAccountStore
from plugins.qqbot.backend.channel import QQBotChannel


class _Accounts:
    def __init__(self):
        self.roles = {}
        self.avatars = {}

    def register(
        self,
        *,
        platform,
        platform_account_id,
        config_ref,
        role_id,
        display_name=None,
        avatar_url=None,
    ):
        self.roles[platform_account_id] = role_id
        if avatar_url is not None:
            self.avatars[platform_account_id] = avatar_url
        return SimpleNamespace(record=SimpleNamespace(id=platform_account_id))

    def check_owner(self, *, config_ref, role_id, **_identity):
        if not role_id:
            raise ValueError("账号没有所属角色")

    def register_saved(self, *, response_rules=None, **fields):
        # The host refuses an entry without an owner; the plugin must skip it.
        return self.register(**fields) if fields.get("role_id") else None

    def role_exists(self, role_id):
        return True

    def report(self, account_id, **kwargs):
        pass

    def unregister(self, account_id):
        pass


class _Bus:
    def subscribe_outbound(self, channel, callback):
        pass

    def unsubscribe_outbound(self, channel, callback):
        pass


class _Push:
    def register_channel(self, channel, **kwargs):
        pass

    def unregister_channel(self, channel, **kwargs):
        pass


@pytest.mark.asyncio
async def test_one_public_channel_starts_isolated_application_gateways(
    tmp_path, monkeypatch
):
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))
    # Without an owner role the host refuses the application.
    store.save({"app_id": "100", "client_secret": "unowned-secret"})
    store.save(
        {
            "app_id": "200",
            "client_secret": "second-secret",
            "role_id": "other",
            "connected": True,
            "targets": [],
        }
    )
    manager = QQBotAccountsChannel(SimpleNamespace(accounts=_Accounts()), store, ())
    started = []

    async def start(self, ctx, *, public_hooks=True):
        started.append((self._app_id, public_hooks))

    async def stop(self):
        pass

    monkeypatch.setattr(QQBotChannel, "start", start)
    monkeypatch.setattr(QQBotChannel, "stop", stop)
    runtime = SimpleNamespace(bus=_Bus(), push_tool=_Push(), event_bus=EventBus())
    await manager.start(runtime)
    try:
        # The unowned application is not registered, so it is not served.
        assert started == [("200", False)]
        assert list(manager._channels) == ["200"]
        assert manager._channels["200"]._client_secret == "second-secret"
    finally:
        await manager.stop()


@pytest.mark.asyncio
async def test_connected_avatar_is_stored_reregistered_and_kept_on_failed_refresh(
    tmp_path, monkeypatch, avatar_fetch
):
    avatar = "data:image/png;base64,iVBORw0KGgo="
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))
    store.save({"app_id": "200", "client_secret": "secret", "role_id": "mira"})

    async def start(self, ctx, *, public_hooks=True):
        pass

    async def stop(self):
        pass

    monkeypatch.setattr(QQBotChannel, "start", start)
    monkeypatch.setattr(QQBotChannel, "stop", stop)

    async def connect(fetched: str | None) -> _Accounts:
        avatar_fetch.return_value = fetched
        accounts = _Accounts()
        manager = QQBotAccountsChannel(SimpleNamespace(accounts=accounts), store, ())
        await manager.start(
            SimpleNamespace(bus=_Bus(), push_tool=_Push(), event_bus=EventBus())
        )
        await asyncio.gather(*manager._avatar_tasks.values())
        await manager.stop()
        return accounts

    fetched = await connect(avatar)
    assert store.get("200")["avatar"] == avatar
    assert fetched.avatars["200"] == avatar

    restarted = await connect(None)
    assert restarted.avatars["200"] == avatar
    assert store.get("200")["avatar"] == avatar
