from __future__ import annotations

from shiori_sdk.testing.storage import FakeKV
from plugins.qqbot.backend.account_identity import QQBotAccountIdentity
from plugins.qqbot.backend.accounts import QQBotAccountStore


def test_gateway_status_and_bot_identity_are_account_scoped(tmp_path, setup_context):
    store = QQBotAccountStore(FakeKV())
    for app_id in ("100", "200"):
        store.save(
            {"app_id": app_id, "client_secret": f"secret-{app_id}", "role_id": app_id}
        )
    context = setup_context(lambda value: f"account-{value}")
    accounts = context.accounts
    identity = QQBotAccountIdentity(context, store)

    identity.report("100", "online", "", "Bot One", "bot-one")
    identity.report("200", "login_required", "invalid secret", "")

    assert store.get("100")["bot_id"] == "bot-one"
    assert "bot_id" not in store.get("200")
    assert accounts.reports[0][0] == "account-100"
    assert accounts.reports[0][1]["capabilities"]
    assert accounts.reports[1][0] == "account-200"
    assert accounts.reports[1][1]["capabilities"] == frozenset()


def test_candidate_ready_identity_is_not_persisted_before_handover(
    tmp_path, setup_context
):
    store = QQBotAccountStore(FakeKV())
    store.save({"app_id": "100", "client_secret": "working", "role_id": "mira"})
    identity = QQBotAccountIdentity(
        setup_context(lambda value: f"account-{value}"), store
    )

    identity.begin_handoff("100")
    identity.report("100", "online", "", "Replacement", "new-bot")

    assert identity.pending_identity("100") == ("Replacement", "new-bot")
    assert "bot_id" not in store.get("100")
    identity.end_handoff("100")


def test_via_account_names_the_application_and_its_bot(tmp_path, setup_context):
    store = QQBotAccountStore(FakeKV())
    store.save({"app_id": "100", "client_secret": "s", "role_id": "mira"})
    identity = QQBotAccountIdentity(
        setup_context(lambda value: f"account-{value}"), store
    )
    assert identity.via_account("100")["prefix"] == "QQ 机器人（AppID 100）"

    identity.report("100", "online", "", "Bot One", "bot-one")
    assert identity.via_account("100") == {
        "platform": "qqbot",
        "platform_account_id": "100",
        "display_name": "Bot One",
        "prefix": "QQ 机器人「Bot One」（AppID 100）",
    }
