import asyncio
import json
import httpx
import pytest
from unittest.mock import AsyncMock
from shiori_sdk.messages import OutboundMessage
from shiori_sdk.memory.committed import TurnCommitted
from shiori_sdk.accounts.targets import UncertainDeliveryError
from plugins.grok_bot.backend.protocol import BotMessage, CallbackError


async def test_start_is_ready_without_probe_and_messages_still_require_auth(harness):
    connection = harness.connection
    assert connection.status()["connected"]
    assert harness.requests == []
    settings = json.loads(connection.client_file.read_text(encoding="utf-8"))
    assert set(settings) == {"protocol", "callback_url", "token"}
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.post(
            settings["callback_url"] + "messages",
            json={"message_id": "blocked", "text": "hello"},
        )
        assert response.status_code == 401
        removed = await client.post(
            settings["callback_url"] + "handshake",
            json={},
            headers={"Authorization": f"Bearer {settings['token']}"},
        )
        assert removed.status_code == 404
    await connection.send(BotMessage("first", "hello"))
    assert [request["type"] for request in harness.requests] == ["message"]
    assert "token" not in json.dumps(harness.requests)


async def test_private_inbound_duplicate_normal_reply_and_proactive_use_one_conversation(
    harness,
):
    connection = harness.connection
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
    assert connection.journal.state.exchanges["silent"].count == 1
    assert harness.requests == []


async def test_failed_intake_same_id_retry_is_recovered_once_without_restart(
    harness, monkeypatch
):
    connection = harness.connection
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
    assert connection.journal.state.exchanges["retry-same-id"].count == 1


async def test_committed_response_keeps_its_parent_pending_until_channel_delivery(
    harness,
):
    connection = harness.connection
    await connection.receive(
        "messages", {"message_id": "waiting-for-delivery", "text": "hello"}
    )
    harness.bus.pending_outbound.add(
        (connection.name, connection.config.chat_id, "waiting-for-delivery")
    )
    await harness.events.emit(
        TurnCommitted(
            session_key="role:mira",
            channel=connection.name,
            chat_id=connection.config.chat_id,
            input_message="hello",
            persisted_user_message="hello",
            assistant_response="reply",
            tools_used=[],
            external_message_id="waiting-for-delivery",
        )
    )
    assert [message.message_id for message in connection.journal.pending()] == [
        "waiting-for-delivery"
    ]
    await harness.bus.publish_outbound(
        OutboundMessage(
            channel=connection.name,
            chat_id=connection.config.chat_id,
            content="reply",
            metadata={"external_message_id": "waiting-for-delivery"},
            committed_message_id="response",
        )
    )
    assert connection.journal.pending() == []


async def test_suppressed_nonempty_committed_reply_releases_parent_without_channel_send(
    harness,
):
    connection = harness.connection
    await connection.receive(
        "messages", {"message_id": "tool-delivered", "text": "hello"}
    )
    await harness.events.emit(
        TurnCommitted(
            session_key="role:mira",
            channel=connection.name,
            chat_id=connection.config.chat_id,
            input_message="hello",
            persisted_user_message="hello",
            assistant_response="sent using account_send",
            tools_used=[],
            external_message_id="tool-delivered",
        )
    )
    assert connection.journal.pending() == []
    assert "tool-delivered" not in connection._submitted
    assert harness.requests == []


@pytest.mark.parametrize("pending_reply", [False, True])
async def test_reconnect_keeps_only_replies_still_queued_on_host_bus(
    harness, monkeypatch, pending_reply
):
    from plugins.grok_bot.backend.connection import GrokConnection

    old = harness.connection
    await old.receive("messages", {"message_id": "parent", "text": "hello"})
    ctx = old._ctx
    assert ctx is not None
    if pending_reply:
        harness.bus.pending_outbound.add((old.name, old.config.chat_id, "parent"))
    await old.stop()
    restored = GrokConnection(
        old.config,
        old.journal._kv,
        old.client_file.parent.parent,
        old.client_path,
        config_changed=lambda value: None,
        status_changed=lambda state, error: None,
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )
    harness.connection = restored
    try:
        await restored.start(ctx)
        assert restored._recovery is not None
        await restored._recovery
        assert len(harness.bus.inbound) == 1
        assert bool(restored.journal.pending()) is pending_reply
        assert ("parent" in restored._submitted) is pending_reply
        monkeypatch.setattr("plugins.grok_bot.backend.exchange.MAX_RECORDS", 4)
        for index in range(4):
            await restored.send(BotMessage(f"other-{index}", "new topic"))
        assert ("parent" in restored.journal.state.messages) is pending_reply
        if pending_reply:
            await harness.bus.publish_outbound(
                OutboundMessage(
                    channel=restored.name,
                    chat_id=restored.config.chat_id,
                    content="queued reply",
                    metadata={"external_message_id": "parent"},
                    committed_message_id="response",
                )
            )
            assert harness.hub.deliveries[-1]["delivery_status"] == "sent"
            assert restored.journal.pending() == []
    finally:
        await restored.stop()


async def test_uncertain_send_is_visible_and_replay_never_reposts(harness, monkeypatch):
    connection = harness.connection
    post = AsyncMock(side_effect=UncertainDeliveryError("uncertain"))
    monkeypatch.setattr(connection._transport, "post", post)
    message = BotMessage("uncertain", "hello")
    with pytest.raises(UncertainDeliveryError):
        await connection.send(message)
    assert connection.journal.state.messages[message.message_id].state == "uncertain"
    assert connection.status()["detail"] == ""
    with pytest.raises(CallbackError):
        await connection.send(message)
    post.assert_awaited_once()


async def test_interleaved_reply_chains_send_with_their_own_budget_and_correlation(
    harness,
):
    connection = harness.connection
    for index in range(8):
        parent = f"a{index - 1}" if index else ""
        if index % 2:
            await connection.send(BotMessage(f"a{index}", "reply", parent))
        else:
            await connection.receive(
                "messages",
                {"message_id": f"a{index}", "text": "hello", "reply_to": parent},
            )
    await connection.send(BotMessage("b0", "new topic"))
    await connection.receive(
        "messages", {"message_id": "a8", "text": "hello", "reply_to": "a7"}
    )
    await connection.send(BotMessage("a9", "reply", "a8"))
    await connection.receive(
        "messages", {"message_id": "b1", "text": "hello", "reply_to": "b0"}
    )
    assert (await connection.send(BotMessage("b2", "reply", "b1")))["accepted"]
    assert harness.requests[-1]["exchange_id"] == "b0"
    assert harness.requests[-1]["reply_to"] == "b1"
    assert connection.journal.state.exchanges["a0"].count == 10
    assert connection.journal.state.exchanges["b0"].count == 3
