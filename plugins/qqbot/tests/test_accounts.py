from __future__ import annotations

from agent.plugin_host.kv import PluginKVStore
from agent import config as agent_config
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


def test_workspace_file_reference_remains_usable_after_migration(tmp_path, monkeypatch):
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "QQBOT_SECRET").write_text("file-secret", encoding="utf-8")
    monkeypatch.delenv("QQBOT_SECRET", raising=False)
    monkeypatch.setattr(agent_config, "resolve_default_workspace", lambda: tmp_path)
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))
    store.migrate_legacy("100", "${QQBOT_SECRET}")

    assert resolve_secret(store.get("100")["client_secret"]) == "file-secret"
