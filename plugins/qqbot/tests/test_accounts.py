"""Credential references stay stored verbatim and resolve only when used."""

from shiori_sdk.testing.extensions import FakeConfig
from shiori_sdk.testing.storage import FakeKV
from plugins.qqbot.backend.accounts import QQBotAccountStore, resolve_secret


def test_environment_reference_resolves_only_for_runtime():
    config = FakeConfig()
    config.references["${QQBOT_SECRET}"] = "runtime-secret"
    assert (
        resolve_secret("${QQBOT_SECRET}", config.resolve_reference) == "runtime-secret"
    )
    assert (
        resolve_secret("literal-secret", config.resolve_reference) == "literal-secret"
    )
    assert resolve_secret("${MISSING}", config.resolve_reference) == ""


def test_workspace_reference_resolution_keeps_the_stored_secret():
    config = FakeConfig()
    config.references["${QQBOT_SECRET}"] = "file-secret"
    store = QQBotAccountStore(FakeKV())
    store.save({"app_id": "100", "client_secret": "${QQBOT_SECRET}"})
    assert (
        resolve_secret(store.get("100")["client_secret"], config.resolve_reference)
        == "file-secret"
    )
    assert store.get("100")["client_secret"] == "${QQBOT_SECRET}"
