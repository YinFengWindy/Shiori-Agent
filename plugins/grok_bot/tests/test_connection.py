import asyncio
import json
import httpx
import pytest
from unittest.mock import AsyncMock
from shiori_sdk.messages import OutboundMessage
from shiori_sdk.memory.committed import TurnCommitted
from shiori_sdk.accounts.targets import UncertainDeliveryError
from plugins.grok_bot.backend.protocol import BotMessage, CallbackError


async def handshake(connection):
    await connection.probe()
    settings = json.loads(connection.client_file.read_text(encoding="utf-8"))
    return await connection.receive(
        "handshake",
        {"protocol": settings["protocol"], "challenge": settings["challenge"]},
    )


async def test_probe_is_not_online_until_authenticated_handshake(harness):
    connection = harness.connection
    assert not connection.status()["connected"]
    with pytest.raises(CallbackError, match="回程验证"):
        await connection.receive("messages", {"message_id": "in", "text": "hello"})
    await connection.probe()
    assert not connection.status()["connected"]
    with pytest.raises(CallbackError, match="过期"):
        await connection.receive(
            "handshake", {"protocol": "shiori-grok/1", "challenge": "old"}
        )
    assert await handshake(connection) == (200, {"status": "connected"})
    assert connection.status()["connected"]
    assert "token" not in json.dumps(harness.requests)


async def test_private_inbound_duplicate_normal_reply_and_proactive_use_one_conversation(
    harness,
):
    connection = harness.connection
    await handshake(connection)
    settings = json.loads(connection.client_file.read_text(encoding="utf-8"))
    async with httpx.AsyncClient(
        trust_env=False, headers={"Authorization": f"Bearer {settings['token']}"}
    ) as client:
        body = {"message_id": "bot-1", "text": "你好"}
        response = await client.post(settings["callback_url"] + "messages", json=body)
        assert response.status_code == 202
        duplicate = await client.post(settings["callback_url"] + "messages", json=body)
        assert duplicate.json()["status"] == "duplicate"
        forged = await client.post(
            settings["callback_url"] + "messages", json={**body, "role_id": "other"}
        )
        assert forged.status_code == 400
    [incoming] = harness.bus.inbound
    assert incoming.metadata["role_id"] == "mira"
    assert incoming.sender == connection.config.peer_id
    assert incoming.chat_id == connection.config.chat_id
    assert incoming.metadata["source"] == "role_account"
    await harness.bus.publish_outbound(
        OutboundMessage(
            channel=connection.name,
            chat_id=incoming.chat_id,
            content="收到",
            metadata={"external_message_id": "bot-1"},
            committed_message_id="committed-1",
        )
    )
    assert harness.requests[-1]["reply_to"] == "bot-1"
    assert harness.hub.deliveries[-1]["delivery_status"] == "sent"
    receipt = await connection.send(BotMessage("proactive-1", "我有事找你"))
    assert receipt["accepted"] is True
    assert "message_id" not in receipt
    assert receipt["conversation"] == {
        "channel": connection.name,
        "chat_id": incoming.chat_id,
        "chat_type": "private",
    }
    assert connection.journal.pending() == []
    connection.pause_intake()
    with pytest.raises(CallbackError, match="暂停"):
        await connection.receive("messages", {"message_id": "paused", "text": "hi"})
    await connection.stop()
    assert connection.name not in harness.bus.outbound
    assert not connection.client_file.exists()


async def test_callbacks_are_serialized_and_bind_peer_identity(harness):
    connection = harness.connection
    await handshake(connection)
    await asyncio.gather(
        *(
            connection.receive(
                "messages", {"message_id": f"bot-{index}", "text": str(index)}
            )
            for index in range(4)
        )
    )
    assert [message.content for message in harness.bus.inbound] == ["0", "1", "2", "3"]
    assert {message.sender for message in harness.bus.inbound} == {
        connection.config.peer_id
    }


async def test_no_reply_committed_turn_releases_pending_input_without_network_reply(
    harness,
):
    connection = harness.connection
    await handshake(connection)
    await connection.receive("messages", {"message_id": "silent", "text": "不用回复"})
    assert len(connection.journal.pending()) == 1
    await harness.events.emit(
        TurnCommitted(
            session_key="role:mira",
            channel=connection.name,
            chat_id=connection.config.chat_id,
            input_message="不用回复",
            persisted_user_message="不用回复",
            assistant_response="",
            tools_used=[],
            external_message_id="silent",
        )
    )
    assert connection.journal.pending() == []
    connection.journal.reset()
    assert connection.journal.state.count == 0
    assert all(request["type"] == "connection_check" for request in harness.requests)


async def test_failed_intake_same_id_retry_is_recovered_once_without_restart(
    harness, monkeypatch
):
    connection = harness.connection
    await handshake(connection)
    intake = connection._intake
    original = intake.submit
    monkeypatch.setattr(
        intake, "submit", AsyncMock(side_effect=RuntimeError("admission failed"))
    )
    payload = {"message_id": "retry-same-id", "text": "hello"}
    with pytest.raises(RuntimeError):
        await connection.receive("messages", payload)
    assert harness.bus.inbound == []
    monkeypatch.setattr(intake, "submit", original)
    assert (await connection.receive("messages", payload))[0] == 202
    assert (await connection.receive("messages", payload))[1]["status"] == "duplicate"
    assert len(harness.bus.inbound) == 1
    assert connection.journal.state.count == 1


async def test_uncertain_send_is_visible_and_replay_never_reposts(harness, monkeypatch):
    connection = harness.connection
    await handshake(connection)
    post = AsyncMock(side_effect=UncertainDeliveryError("uncertain"))
    monkeypatch.setattr(connection._transport, "post", post)
    message = BotMessage("uncertain", "hello")
    with pytest.raises(UncertainDeliveryError):
        await connection.send(message)
    assert connection.journal.state.messages[message.message_id].state == "uncertain"
    assert "不确定" in connection.status()["detail"]
    with pytest.raises(CallbackError):
        await connection.send(message)
    post.assert_awaited_once()
