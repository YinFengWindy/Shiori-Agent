"""Natural route resolution remains separate from explicit Bot sends."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.grok_bot.backend.delivery import GrokDelivery


async def test_resolver_uses_configured_connection_without_sending(monkeypatch):
    connection = SimpleNamespace(
        name="grok_bot_one",
        config=SimpleNamespace(peer_id="peer", chat_id="dm:peer"),
        send=AsyncMock(return_value={"accepted": True}),
    )

    def connection_for(payload):
        if payload["account_id"] != "one":
            raise ValueError("unknown account")
        return connection

    delivery = GrokDelivery(SimpleNamespace(connection_for=connection_for))
    payload = {
        "account_id": "one",
        "target_kind": "private",
        "target_id": "peer",
        "message": "raw payload",
    }
    assert await delivery.resolve(payload) == {
        "channel": "grok_bot_one",
        "chat_id": "dm:peer",
        "chat_type": "private",
    }
    connection.send.assert_not_awaited()
    with pytest.raises(ValueError):
        await delivery.resolve({**payload, "account_id": "other"})
    with pytest.raises(ValueError):
        await delivery.resolve({**payload, "target_id": "different-peer"})
    monkeypatch.setattr(
        delivery,
        "resolve",
        AsyncMock(side_effect=AssertionError("ordinary sends must not resolve")),
    )
    assert await delivery.send(payload) == {"accepted": True}
    assert connection.send.await_args.args[0].text == "raw payload"
