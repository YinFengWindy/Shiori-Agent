from __future__ import annotations

from pathlib import Path

import pytest

from plugins.qq.backend.channel.formatting import GROUP_PREFIX
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig
from plugins.qq.backend.napcat_account_files import NapCatAccountFiles
from shiori_sdk.accounts import AccountResponseRules
from plugins.qq.backend.plugin import setup
from shiori_sdk.testing.channel_context import (
    FakeChannelPluginContext,
    FakeChannelDeclarations,
)
from plugins.qq.backend.plugin import _cancel, _send_account

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_manifest_preserves_historical_channel_name() -> None:
    # Historical conversation keys retain the original QQ channel name.
    manifest = FakeChannelDeclarations(PLUGIN_DIR)
    assert manifest is not None
    assert manifest.values["id"] == "qq"
    assert manifest.values["display_name"] == "QQ（NapCat）"
    assert set(manifest.values["capabilities"]) == {
        "channels",
        "accounts",
        "avatars",
        "processes",
        "http",
        "workspace",
        "rpc",
    }
    assert manifest.values.get("config_model") is None
    assert [item["name"] for item in manifest.values["channels"]] == ["qq"]
    # NapCat delivers every group message, so its groups can be listened to.
    assert manifest.values["channels"][0]["group_listening"] is True


def test_manifest_group_prefix_matches_the_transport_group_format() -> None:
    # Account intake and outbound target validation share the group prefix.
    manifest = FakeChannelDeclarations(PLUGIN_DIR)
    assert manifest is not None
    types = {item.type: item.prefix for item in manifest.channel_chat_types("qq")}
    assert types == {"private": None, "group": GROUP_PREFIX}


@pytest.mark.asyncio
async def test_shared_account_send_adapts_target_and_rejects_topic() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    via = QQConnectionConfig(
        ref="a", ws_uri="ws://127.0.0.1:1", ws_token="t", expected_uin="101"
    ).via_account()
    runtime = SimpleNamespace(
        send_target=AsyncMock(return_value={"message_id": "9"}),
        via_account=lambda account_id: via,
    )
    payload = {
        "account_id": "account-1",
        "target_kind": "group",
        "target_id": "42",
        "message": "hello",
        "message_thread_id": None,
        "group_id": "",
        "mention_ids": ["902"],
    }
    assert await _send_account(runtime, payload) == {
        "message_id": "9",
        "via_account": via,
    }
    runtime.send_target.assert_awaited_once_with(
        "account-1",
        "group",
        "42",
        "hello",
        group_id="",
        mention_ids=("902",),
        images=(),
    )
    runtime.send_target.reset_mock()
    await _send_account(runtime, {**payload, "media": ["https://x.test/a.png"]})
    assert runtime.send_target.await_args.kwargs["images"] == ("https://x.test/a.png",)
    with pytest.raises(ValueError, match="话题"):
        await _send_account(runtime, {**payload, "message_thread_id": 7})


@pytest.mark.asyncio
async def test_temporary_login_cancel_forwards_role_to_runtime() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    runtime = SimpleNamespace(cancel_login=AsyncMock())
    assert await _cancel(runtime, {"ref": "aa", "role_id": "mira"}) == {"ok": True}
    runtime.cancel_login.assert_awaited_once_with("aa", "mira")


@pytest.mark.asyncio
async def test_plugin_contributes_one_account_channel(tmp_path):
    ctx = FakeChannelPluginContext("qq", PLUGIN_DIR)
    ctx.workspace = tmp_path
    try:
        await setup(ctx.as_capability())
        [channel] = ctx.channels.channels
        assert channel.name == "qq"
        assert channel.configuration_key[0] == "qq-accounts"
        await channel.stop()
    finally:
        await ctx.aclose()


def _verified(ref: str, uin: str, role_id: str) -> QQConnectionConfig:
    return QQConnectionConfig(
        ref,
        "ws://127.0.0.1:1",
        f"secret-{ref}",
        expected_uin=uin,
        auto_connect=False,
        verified=True,
        role_id=role_id,
    )


async def _load(workspace: Path, roles: set[str]) -> FakeChannelPluginContext:
    """Runs setup on an existing workspace, as an application start does."""
    ctx = FakeChannelPluginContext("qq", PLUGIN_DIR)
    ctx.workspace = workspace
    ctx.accounts.available_roles = roles
    await setup(ctx.as_capability())
    return ctx


async def _unload(ctx: FakeChannelPluginContext) -> None:
    try:
        for channel in ctx.channels.channels:
            await channel.stop()
    finally:
        await ctx.aclose()


@pytest.mark.asyncio
async def test_load_registers_saved_owners_and_deletes_orphaned_data(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            "aa": _verified("aa", "101", "gone"),
            "cc": _verified("cc", "303", "mira"),
            # Without an owner the data is kept for the user to fix.
            "dd": _verified("dd", "404", ""),
        }
    )
    napcat = NapCatAccountFiles(store.path.parent / "managed-napcat")
    # bb has no saved account: it is a temporary login left after a crash.
    for ref in ("aa", "bb"):
        napcat.account_dir(ref).mkdir(parents=True)

    ctx = await _load(tmp_path, {"mira"})
    try:
        assert {
            snapshot.record.id: snapshot.record.role_id
            for snapshot in ctx.accounts.records.values()
        } == {"qq:303": "mira"}
        assert list(store.load()) == ["cc", "dd"]
        assert "secret-aa" not in store.path.read_text(encoding="utf-8")
        assert not napcat.account_dir("aa").exists()
        assert not napcat.account_dir("bb").exists()
    finally:
        await _unload(ctx)


@pytest.mark.asyncio
async def test_rules_saved_through_the_host_hook_survive_a_restart(tmp_path):
    QQAccountsStore(tmp_path).save({"aa": _verified("aa", "101", "mira")})
    rules = AccountResponseRules(private_enabled=False, blocked_sender_ids=("9",))
    first = await _load(tmp_path, {"mira"})
    try:
        assert first.accounts.rules_handler is not None
        first.accounts.rules_handler("aa", rules)
    finally:
        await _unload(first)

    restarted = await _load(tmp_path, {"mira"})
    try:
        [snapshot] = restarted.accounts.records.values()
        assert (snapshot.record.id, snapshot.record.response_rules) == (
            "qq:101",
            rules,
        )
    finally:
        await _unload(restarted)
