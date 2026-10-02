from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from plugins.feishu.backend.plugin import setup
from shiori_sdk.testing.channel_context import (
    FakeChannelPluginContext,
    FakeChannelDeclarations,
)
from shiori_sdk.testing.accounts import FakeAccounts
from shiori_sdk.accounts.targets import UncertainDeliveryError

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _app(app_id: str, role_id: str = "mira", **extra: Any) -> dict[str, Any]:
    return {
        "app_id": app_id,
        "app_secret": "secret",
        "domain": "feishu",
        "role_id": role_id,
        **extra,
    }


def _fake_ctx(kv: dict[str, Any], handlers: dict[str, Any], channels: list[Any]):
    ctx = FakeChannelPluginContext("feishu", PLUGIN_DIR)
    ctx.kv.values = kv
    ctx.rpc.handlers = handlers
    ctx.channels.channels = channels
    ctx.accounts = FakeAccounts("feishu", id_factory=lambda _value: "account-a")
    ctx.accounts.on_delete = lambda handler: handlers.__setitem__("delete", handler)
    return ctx


@pytest.mark.asyncio
async def test_shared_account_rpc_uses_selected_private_application() -> None:
    handlers: dict[str, Any] = {}
    channels: list[Any] = []
    kv = {"applications": [_app("cli_a")], "targets:feishu:cli_a": {"oc_chat": "u"}}
    await setup(_fake_ctx(kv, handlers, channels))
    assert (
        await handlers["account.targets"]({"account_id": "account-a", "kind": "known"})
    )["coverage"] == "observed_private_chats"
    [group] = channels
    member = group.member("feishu:cli_a")
    assert member.name == "feishu:feishu:cli_a"
    member.send = AsyncMock(return_value="om_9")
    request = {
        "account_id": "account-a",
        "target_kind": "private",
        "target_id": "oc_chat",
        "message": "hello",
    }
    assert await handlers["account.send"](request) == {
        "message_id": "om_9",
        "via_account": member.via_account(),
    }
    assert member.via_account()["platform_account_id"] == "feishu:cli_a"
    member.send.assert_awaited_once_with("oc_chat", "hello")
    member.send.return_value = None
    with pytest.raises(UncertainDeliveryError):
        await handlers["account.send"](request)
    member.send.side_effect = httpx.ReadTimeout("reply lost")
    with pytest.raises(UncertainDeliveryError):
        await handlers["account.send"](request)
    with pytest.raises(ValueError, match="私聊"):
        await handlers["account.send"](
            {"account_id": "account-a", "target_kind": "group"}
        )


@pytest.mark.asyncio
async def test_stored_bot_avatar_is_registered_on_load() -> None:
    avatar = "data:image/png;base64,iVBORw0KGgo="
    kv = {
        "applications": [_app("cli_a", connection_enabled=False)],
        "profile:feishu:cli_a": {"name": "Bot", "avatar": avatar},
    }
    ctx = _fake_ctx(kv, {}, [])
    registered: list[dict[str, Any]] = []
    register_saved = ctx.accounts.register_saved

    def capture(**kwargs):
        registered.append(kwargs)
        return register_saved(**kwargs)

    ctx.accounts.register_saved = capture

    await setup(ctx)

    assert [row["avatar_url"] for row in registered] == [avatar]


@pytest.mark.asyncio
async def test_delete_hook_closes_the_websocket_before_purging() -> None:
    handlers: dict[str, Any] = {}
    channels: list[Any] = []
    kv: dict[str, Any] = {
        "applications": [_app("cli_a")],
        "profile:feishu:cli_a": {},
        "targets:feishu:cli_a": {},
    }
    await setup(_fake_ctx(kv, handlers, channels))
    [group] = channels
    channel = group.member("feishu:cli_a")
    order: list[str] = []
    channel.stop = AsyncMock(side_effect=lambda: order.append(f"stop:{len(kv)}"))

    plan = handlers["delete"]("feishu:cli_a")
    # Planning is side-effect free; disconnect closes before purge deletes.
    assert order == [] and len(kv) == 3
    await plan.disconnect()
    await plan.purge()
    assert order == ["stop:3"]
    assert kv == {"applications": []}
    assert channel._accounts is None
    repeated = handlers["delete"]("feishu:cli_a")
    await repeated.disconnect()
    await repeated.purge()
    assert channel.stop.await_count == 1


def test_manifest_declares_the_feishu_channel_for_binding_discovery() -> None:
    manifest = FakeChannelDeclarations(PLUGIN_DIR)

    assert manifest is not None
    assert manifest.values["display_name"] == "飞书"
    assert manifest.values.get("config_model") is None
    [channel] = manifest.values["channels"]
    assert (channel["name"], channel["label"]) == ("feishu", "飞书")
    # Private-only: there is no group blacklist whose member IDs need a label.
    assert channel.get("contact_label") is None
    [private] = manifest.channel_chat_types("feishu")
    assert (private.type, private.prefix) == ("private", None)
    assert (private.chat_id_hint or "").startswith("oc_")
