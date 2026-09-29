"""Account model tools select a channel and never show the model account IDs."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.account_delivery import AccountSendReceipt
from agent.tools.account_delivery import (
    AccountListTool,
    AccountSendTool,
    AccountTargetsTool,
)
from core.accounts.target_contract import AccountTarget


@pytest.mark.asyncio
async def test_account_tools_pass_the_channel_and_hide_account_ids() -> None:
    delivery = SimpleNamespace(
        list_channels=lambda role_id: [{"channel": "qq", "online": True}],
        targets=AsyncMock(return_value={"scope": "known", "items": [{"id": "42"}]}),
        send=AsyncMock(
            return_value=AccountSendReceipt(
                attempt_id="attempt-1",
                account_id="qq:101",
                channel="qq",
                target_kind="group",
                target_id="42",
                platform_message_id="platform-9",
                ownership_current=True,
            )
        ),
    )
    listed = json.loads(await AccountListTool(delivery).execute(role_id="mira"))
    targets = json.loads(
        await AccountTargetsTool(delivery).execute(
            channel="qq", role_id="mira", kind="known"
        )
    )
    receipt = json.loads(
        await AccountSendTool(delivery).execute(
            channel="qq",
            role_id="mira",
            target_kind="group",
            target_id="42",
            message="hello",
            mention_ids=["902"],
        )
    )
    assert listed == [{"channel": "qq", "online": True}]
    assert targets["items"] == [{"id": "42"}]
    delivery.targets.assert_awaited_once_with("qq", "mira", "known", "", "")
    assert receipt["platform_message_id"] == "platform-9"
    assert receipt["channel"] == "qq"
    assert "qq:101" not in json.dumps(receipt)
    delivery.send.assert_awaited_once_with(
        "qq",
        "mira",
        AccountTarget("group", "42", mention_ids=("902",)),
        "hello",
        media=[],
    )
    for tool in (AccountTargetsTool, AccountSendTool):
        assert "account_id" not in tool.parameters["properties"]
        assert "channel" in tool.parameters["required"]


@pytest.mark.asyncio
async def test_account_send_passes_images_without_text() -> None:
    receipt = AccountSendReceipt(
        attempt_id="attempt-1",
        account_id="qq:101",
        channel="qq",
        target_kind="private",
        target_id="42",
        platform_message_id="platform-9",
        ownership_current=True,
    )
    delivery = SimpleNamespace(send=AsyncMock(return_value=receipt))
    await AccountSendTool(delivery).execute(
        channel="qq",
        role_id="mira",
        target_kind="private",
        target_id="42",
        media=["D:/media/scene.png", "https://example.test/a.png"],
    )
    delivery.send.assert_awaited_once_with(
        "qq",
        "mira",
        AccountTarget("private", "42"),
        "",
        media=["D:/media/scene.png", "https://example.test/a.png"],
    )
    with pytest.raises(ValueError, match="media"):
        await AccountSendTool(delivery).execute(
            channel="qq",
            role_id="mira",
            target_kind="private",
            target_id="42",
            media="D:/media/scene.png",
        )
