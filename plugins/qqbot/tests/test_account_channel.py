from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.plugin_host.kv import PluginKVStore
from bus.event_bus import EventBus
from plugins.qqbot.backend.account_channel import QQBotAccountsChannel
from plugins.qqbot.backend.accounts import QQBotAccountStore
from plugins.qqbot.backend.channel import QQBotChannel


class _Accounts:
    def register(self, *, platform, platform_account_id, config_ref, display_name=None):
        return SimpleNamespace(record=SimpleNamespace(id=platform_account_id))

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
    store.migrate_legacy("100", "legacy-secret")
    store.save(
        {
            "app_id": "200",
            "client_secret": "second-secret",
            "legacy": False,
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
        assert started == [("100", False), ("200", False)]
        assert manager._for_chat("c2c:legacy-user")._app_id == "100"
        assert manager._for_chat("c2c:200:opaque-user")._app_id == "200"
        assert manager._channels["100"]._client_secret == "legacy-secret"
        assert manager._channels["200"]._client_secret == "second-secret"
    finally:
        await manager.stop()
