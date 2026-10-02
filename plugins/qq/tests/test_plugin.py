from __future__ import annotations

from pathlib import Path

import pytest

from plugins.qq.backend.channel.formatting import GROUP_PREFIX
from plugins.qq.backend.accounts_store import QQConnectionConfig
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
