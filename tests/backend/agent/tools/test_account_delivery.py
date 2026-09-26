"""Account model tools serialize structured service results without losing IDs."""

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


@pytest.mark.asyncio
async def test_account_tools_expose_structured_service_results() -> None:
    delivery = SimpleNamespace(
        list_accounts=lambda role_id: [{"account_id": "one", "online": True}],
        targets=AsyncMock(return_value={"scope": "known", "items": [{"id": "42"}]}),
        send=AsyncMock(
            return_value=AccountSendReceipt(
                attempt_id="attempt-1",
                account_id="one",
                target_kind="private",
                target_id="42",
                platform_message_id="platform-9",
                ownership_current=True,
            )
        ),
    )
    listed = json.loads(await AccountListTool(delivery).execute(role_id="mira"))
    targets = json.loads(
        await AccountTargetsTool(delivery).execute(
            account_id="one", role_id="mira", kind="known"
        )
    )
    receipt = json.loads(
        await AccountSendTool(delivery).execute(
            account_id="one",
            role_id="mira",
            target_kind="private",
            target_id="42",
            message="hello",
        )
    )
    assert listed == [{"account_id": "one", "online": True}]
    assert targets["items"] == [{"id": "42"}]
    assert receipt["attempt_id"] == "attempt-1"
    assert receipt["platform_message_id"] == "platform-9"
    delivery.send.assert_awaited_once_with(
        "one", "mira", "private", "42", "hello", None
    )
