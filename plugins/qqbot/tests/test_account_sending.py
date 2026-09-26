from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from plugins.qqbot.backend.account_sending import _AccountSendingMixin


class _Sending(_AccountSendingMixin):
    def __init__(self, channel):
        self._channels = {"100": channel}
        self._identity = SimpleNamespace(
            app_for_account=lambda payload: (
                "100" if payload["account_id"] == "account-100" else None
            )
        )


@pytest.mark.asyncio
async def test_send_returns_official_receipt_from_selected_application():
    sent = []

    async def send(chat_id, content):
        sent.append((chat_id, content))
        return "platform-message-id"

    channel = SimpleNamespace(_chat_id=lambda openid: f"c2c:100:{openid}", send=send)
    result = await _Sending(channel).send_target(
        {"account_id": "account-100", "user_openid": "opaque", "content": "hello"}
    )
    assert result == {
        "message_id": "platform-message-id",
        "chat_id": "c2c:100:opaque",
    }
    assert sent == [("c2c:100:opaque", "hello")]

    shared = await _Sending(channel).account_send(
        {
            "account_id": "account-100",
            "target_kind": "private",
            "target_id": "opaque",
            "message": "again",
        }
    )
    assert shared["message_id"] == "platform-message-id"
    assert sent[-1] == ("c2c:100:opaque", "again")
    legacy = await _Sending(channel).account_send(
        {"account_id": "account-100", "user_openid": "opaque", "content": "old"}
    )
    assert legacy["message_id"] == "platform-message-id"
    assert sent[-1] == ("c2c:100:opaque", "old")
    with pytest.raises(ValueError, match="私聊"):
        await _Sending(channel).account_send(
            {"account_id": "account-100", "target_kind": "group"}
        )


@pytest.mark.asyncio
async def test_send_reports_platform_failure_reason():
    request = httpx.Request(
        "POST", "https://api.sgroup.qq.com/v2/users/opaque/messages"
    )
    response = httpx.Response(
        403, json={"message": "target unavailable"}, request=request
    )

    async def denied(chat_id, content):
        raise httpx.HTTPStatusError("rejected", request=request, response=response)

    channel = SimpleNamespace(_chat_id=lambda openid: f"c2c:100:{openid}", send=denied)
    with pytest.raises(RuntimeError, match="HTTP 403.*target unavailable"):
        await _Sending(channel).send_target(
            {"account_id": "account-100", "user_openid": "opaque", "content": "hello"}
        )
