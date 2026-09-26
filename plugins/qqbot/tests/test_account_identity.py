from __future__ import annotations

from types import SimpleNamespace

from agent.plugin_host.kv import PluginKVStore
from plugins.qqbot.backend.account_identity import QQBotAccountIdentity
from plugins.qqbot.backend.accounts import QQBotAccountStore


class _Accounts:
    def __init__(self):
        self.reports = []

    def register(self, *, platform, platform_account_id, config_ref, display_name=None):
        assert platform == "qqbot"
        assert config_ref == f"app:{platform_account_id}"
        return SimpleNamespace(
            record=SimpleNamespace(id=f"account-{platform_account_id}")
        )

    def report(self, account_id, **kwargs):
        self.reports.append((account_id, kwargs))

    def unregister(self, account_id):
        pass


def test_gateway_status_and_bot_identity_are_account_scoped(tmp_path):
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))
    store.migrate_legacy("100", "secret-100")
    store.migrate_legacy("200", "secret-200")
    accounts = _Accounts()
    identity = QQBotAccountIdentity(SimpleNamespace(accounts=accounts), store)

    identity.report("100", "online", "", "Bot One", "bot-one")
    identity.report("200", "login_required", "invalid secret", "")

    assert store.get("100")["bot_id"] == "bot-one"
    assert "bot_id" not in store.get("200")
    assert accounts.reports[0][0] == "account-100"
    assert accounts.reports[0][1]["capabilities"]
    assert accounts.reports[1][0] == "account-200"
    assert accounts.reports[1][1]["capabilities"] == frozenset()


def test_candidate_ready_identity_is_not_persisted_before_handover(tmp_path):
    store = QQBotAccountStore(PluginKVStore(tmp_path / "qqbot.json"))
    store.migrate_legacy("100", "working")
    identity = QQBotAccountIdentity(SimpleNamespace(accounts=_Accounts()), store)

    identity.begin_handoff("100")
    identity.report("100", "online", "", "Replacement", "new-bot")

    assert identity.pending_identity("100") == ("Replacement", "new-bot")
    assert "bot_id" not in store.get("100")
    identity.end_handoff("100")
