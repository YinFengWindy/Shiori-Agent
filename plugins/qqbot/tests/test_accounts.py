from __future__ import annotations

from agent.plugin_host.kv import PluginKVStore
from plugins.qqbot.backend.accounts import QQBotAccountStore, resolve_secret


def test_legacy_migration_is_idempotent_and_preserves_credentials(tmp_path):
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))

    store.migrate_legacy("app-1", "${QQBOT_SECRET}")
    store.observe("app-1", "user-openid")
    store.migrate_legacy("app-1", "replacement")

    assert store.list() == [
        {
            "app_id": "app-1",
            "client_secret": "${QQBOT_SECRET}",
            "legacy": True,
            "connected": True,
            "targets": ["user-openid"],
        }
    ]


def test_environment_reference_resolves_only_for_runtime(monkeypatch):
    monkeypatch.setenv("QQBOT_SECRET", "runtime-secret")
    assert resolve_secret("${QQBOT_SECRET}") == "runtime-secret"
    assert resolve_secret("literal-secret") == "literal-secret"
