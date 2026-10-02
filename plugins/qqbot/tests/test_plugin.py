"""QQBot declarations and setup exercised through the public SDK only."""

from pathlib import Path
import pytest
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.testing.channel_context import (
    FakeChannelPluginContext,
    FakeChannelDeclarations,
)
from plugins.qqbot.backend.plugin import setup
from plugins.qqbot.backend.account_channel import QQBotAccountsChannel
from plugins.qqbot.backend.channel import QQBotChannel

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_qqbot_manifest_declares_its_channel_for_binding_discovery() -> None:
    manifest = FakeChannelDeclarations(PLUGIN_DIR)
    [channel] = manifest.values["channels"]
    assert channel["name"] == "qqbot"
    assert channel["label"] == "QQBot"
    assert channel.get("contact_label") is None
    [private] = manifest.channel_chat_types("qqbot")
    assert (private.type, private.prefix) == ("private", "c2c:")


@pytest.mark.asyncio
async def test_qqbot_plugin_exposes_an_empty_account_channel() -> None:
    ctx = FakeChannelPluginContext("qqbot", PLUGIN_DIR)
    try:
        await setup(ctx.as_capability())
        [channel] = ctx.channels.channels
        assert isinstance(channel, QQBotAccountsChannel)
        assert channel.name == "qqbot"
        assert channel._channels == {}
        assert set(ctx.rpc.handlers) == {
            "account.detail",
            "account.targets",
            "account.save",
            "account.disconnect",
            "account.send",
        }
    finally:
        await ctx.aclose()


def test_qqbot_channel_does_not_consume_bot_commands() -> None:
    assert getattr(QQBotChannel, "uses_bot_commands", False) is False


@pytest.mark.asyncio
async def test_setup_persists_rules_and_deletion_through_registered_hooks() -> None:
    ctx = FakeChannelPluginContext("qqbot", PLUGIN_DIR)
    ctx.kv.set(
        "application_accounts",
        [{"app_id": "100", "client_secret": "secret", "role_id": "mira"}],
    )
    try:
        await setup(ctx.as_capability())
        assert ctx.accounts.rules_handler is not None
        ctx.accounts.rules_handler(
            "app:100", AccountResponseRules(private_enabled=False)
        )
        [channel] = ctx.channels.channels
        assert isinstance(channel, QQBotAccountsChannel)
        assert channel._store.get("100")["response_rules"]["private_enabled"] is False
        assert ctx.accounts.delete_handler is not None
        plan = ctx.accounts.delete_handler("app:100")
        await plan.disconnect()
        await plan.purge()
        assert channel._store.list() == []
    finally:
        await ctx.aclose()


@pytest.mark.asyncio
async def test_restart_keeps_saved_rules_and_purges_apps_of_deleted_roles() -> None:
    first = FakeChannelPluginContext("qqbot", PLUGIN_DIR)
    first.kv.set(
        "application_accounts",
        [
            {"app_id": app_id, "client_secret": f"secret-{app_id}", "role_id": role}
            for app_id, role in (("100", "mira"), ("300", "gone"))
        ],
    )
    first.accounts.available_roles = {"mira", "gone"}
    rules = AccountResponseRules(private_enabled=False, blocked_sender_ids=("spam",))
    try:
        await setup(first.as_capability())
        assert first.accounts.rules_handler is not None
        first.accounts.rules_handler("app:100", rules)
    finally:
        await first.aclose()

    # The role owning 300 was deleted while the plugin was not loaded.
    restarted = FakeChannelPluginContext("qqbot", PLUGIN_DIR)
    restarted.kv = first.kv
    restarted.accounts.available_roles = {"mira"}
    try:
        await setup(restarted.as_capability())
        assert {
            snapshot.record.id: snapshot.record.response_rules
            for snapshot in restarted.accounts.records.values()
        } == {"qqbot:100": rules}
        stored = restarted.kv.get("application_accounts")
        assert isinstance(stored, list)
        assert [row["app_id"] for row in stored] == ["100"]
    finally:
        await restarted.aclose()
