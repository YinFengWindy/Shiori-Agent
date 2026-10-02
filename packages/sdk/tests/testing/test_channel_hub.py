"""The hub fake admits, projects and records input the way the host hub does."""

import pytest

from shiori_sdk.channels.message_source import (
    REPLY_TO_SENDER_IS_USER_KEY,
    SENDER_IS_USER_KEY,
)
from shiori_sdk.messages import InboundMessage, OutboundMessage
from shiori_sdk.testing.channel_hub import FakeChannelHub


def _message(chat_type: str = "private", **metadata: object) -> InboundMessage:
    return InboundMessage(
        channel="chat",
        sender="u1",
        chat_id="c1",
        content="hello",
        metadata={"chat_type": chat_type, **metadata},
    )


def test_projection_matches_the_host_and_drops_plugin_claimed_user_flags() -> None:
    hub = FakeChannelHub(session_key="role:mira", default_chat_type="private")
    message = InboundMessage(
        "chat",
        "u1",
        "c1",
        "hello",
        metadata={
            "message_id": " m1 ",
            SENDER_IS_USER_KEY: True,
            REPLY_TO_SENDER_IS_USER_KEY: True,
        },
    )

    routed = hub.route_inbound(message)

    assert routed is not message
    assert routed.metadata == {
        "message_id": " m1 ",
        "external_message_id": "m1",
        "role_id": "mira",
        "thread_id": "thread:mira:chat:c1",
        "session_key_override": "role:mira",
        "context_channel": "chat",
        "context_chat_id": "c1",
        "transport_channel": "chat",
        "transport_chat_id": "c1",
        "sender_id": "u1",
        "chat_type": "private",
        "source": "role_account",
    }
    assert message.metadata[SENDER_IS_USER_KEY] is True
    assert routed.session_key == "role:mira"


def test_refused_sender_starts_nothing_and_route_inbound_raises() -> None:
    hub = FakeChannelHub(allowed=False)

    assert hub.route_account_inbound(_message()) is None
    with pytest.raises(PermissionError):
        hub.route_inbound(_message())
    assert len(hub.offered) == 2


def test_group_message_starts_a_turn_only_when_it_addresses_the_account() -> None:
    hub = FakeChannelHub(platform_account_id="bot")
    heard: list[InboundMessage] = []

    assert hub.route_account_inbound(_message("group"), on_heard=heard.append) is None
    assert heard == []
    assert hub.route_account_inbound(_message("group", mentioned=True)) is not None
    replying = _message("group", reply_to_sender_id="bot")
    assert hub.route_account_inbound(replying) is not None


def test_listened_group_message_is_heard_without_duplicate_marking() -> None:
    hub = FakeChannelHub(platform_account_id="bot", listening=True)
    heard: list[InboundMessage] = []

    for _ in range(2):
        unaddressed = _message("group", external_message_id="m1")
        assert hub.route_account_inbound(unaddressed, on_heard=heard.append) is None
    assert [item.metadata.get("conversation_duplicate") for item in heard] == [
        None,
        None,
    ]
    # Listening never stores a turn, so the first turn with the ID is not a replay.
    turn = hub.route_account_inbound(
        _message("group", external_message_id="m1", mentioned=True)
    )
    assert turn is not None and "conversation_duplicate" not in turn.metadata


def test_replayed_turn_is_marked_duplicate_per_thread() -> None:
    hub = FakeChannelHub()

    first = hub.route_inbound(_message(external_message_id="m1"))
    replay = hub.route_inbound(_message(external_message_id="m1"))
    other_chat = hub.route_inbound(
        InboundMessage("chat", "u1", "c2", "hi", metadata={"external_message_id": "m1"})
    )

    assert "conversation_duplicate" not in first.metadata
    assert replay.metadata["conversation_duplicate"] is True
    assert "conversation_duplicate" not in other_chat.metadata


def test_pairing_code_is_claimed_only_by_an_unblocked_sender() -> None:
    hub = FakeChannelHub(pairing_code="PAIR")
    pairing = InboundMessage("chat", "u1", "c1", "PAIR")

    assert hub.claim_pairing(_message(), scope="account") is False
    assert hub.claim_pairing(pairing, scope="account") is True
    blocked = FakeChannelHub(pairing_code="PAIR", blocked=True)
    assert blocked.claim_pairing(pairing, scope="platform") is False
    assert hub.pairings == [("u1", "hello", "account"), ("u1", "PAIR", "account")]
    assert blocked.pairings == [("u1", "PAIR", "platform")]


def test_delivery_receipts_record_status_receipt_and_account() -> None:
    hub = FakeChannelHub()
    message = OutboundMessage(
        "chat",
        "c1",
        "reply",
        metadata={"thread_id": "thread:mira:chat:c1"},
        committed_message_id="committed",
    )
    via = {"platform": "chat", "platform_account_id": "bot"}

    hub.mark_delivery(
        message,
        default_channel="chat",
        delivery_status="sent",
        external_message_id="p1",
        via_account=via,
    )

    assert hub.deliveries == [
        {
            "session_key": "role:mira",
            "chat_id": "c1",
            "message_id": "committed",
            "thread_id": "thread:mira:chat:c1",
            "delivery_status": "sent",
            "external_message_id": "p1",
            "via_account": via,
        }
    ]
    assert hub.delivery_statuses() == ["sent"]
