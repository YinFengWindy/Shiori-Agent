from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

import plugins.qqbot.backend.gateway as gateway_module
from plugins.qqbot.backend.channel import QQBotChannel
from plugins.qqbot.backend.gateway import QQBotAuthenticationError


@pytest.mark.asyncio
async def test_token_error_payload_is_reported_as_authentication_failure():
    channel = QQBotChannel("app", "wrong-secret")
    request = httpx.Request("POST", "https://bots.qq.com/app/getAppAccessToken")
    channel._client.post = AsyncMock(
        return_value=httpx.Response(
            200, json={"code": 112, "message": "invalid secret"}, request=request
        )
    )
    with pytest.raises(QQBotAuthenticationError, match="invalid secret") as failure:
        await channel._get_access_token()
    assert channel._is_auth_error(failure.value)


def test_gateway_rejection_is_authentication_not_network_failure():
    assert QQBotChannel._is_auth_error(QQBotAuthenticationError("网关鉴权失败"))
    assert not QQBotChannel._is_auth_error(RuntimeError("connection dropped"))


@pytest.mark.asyncio
async def test_ready_followed_by_immediate_disconnect_fails_handover():
    channel = QQBotChannel("app", "secret")
    channel._report_status("online")
    channel._report_status("offline", "gateway closed")
    with pytest.raises(RuntimeError, match="网关未就绪"):
        await channel.wait_ready()


@pytest.mark.asyncio
async def test_gateway_disconnect_reports_retry_state(monkeypatch):
    states = []
    channel = QQBotChannel(
        "app", "secret", on_status=lambda *status: states.append(status)
    )
    channel._get_access_token = AsyncMock(return_value="token")
    channel._api_request = AsyncMock(return_value={"url": "wss://gateway"})
    channel._run_gateway = AsyncMock(side_effect=OSError("connection dropped"))

    async def stop_after_retry_delay(seconds):
        assert seconds == 5
        channel._stopped.set()

    monkeypatch.setattr(gateway_module.asyncio, "sleep", stop_after_retry_delay)
    await channel._gateway_loop()
    assert [state[0] for state in states] == ["connecting", "error"]
    assert "connection dropped" in states[-1][1]
