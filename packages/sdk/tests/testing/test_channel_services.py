"""Channel service fakes keep the host's ownership and reply rules."""

from shiori_sdk.messages import OutboundMessage
from shiori_sdk.testing.channel_services import (
    FakeInterruptController,
    FakeMessageBus,
)


def test_interrupt_controller_records_requests_and_answers_with_its_message() -> None:
    controller = FakeInterruptController(message="已中断")

    result = controller.request_interrupt("role:mira", sender="u1")

    assert (result.status, result.session_key, result.message) == (
        "interrupted",
        "role:mira",
        "已中断",
    )
    assert controller.requests == [
        {"session_key": "role:mira", "sender": "u1", "command": "/stop"}
    ]


async def test_message_bus_drops_emptied_channels_and_reports_marked_pending() -> None:
    bus = FakeMessageBus()
    delivered: list[OutboundMessage] = []

    async def deliver(message: OutboundMessage) -> None:
        delivered.append(message)

    bus.subscribe_outbound("chat", deliver)
    await bus.publish_outbound(OutboundMessage("chat", "c1", "reply"))
    bus.unsubscribe_outbound("chat", deliver)

    assert [message.content for message in delivered] == ["reply"]
    assert bus.outbound == {}
    assert bus.has_pending_outbound("chat", "c1", "m1") is False
    bus.pending_outbound.add(("chat", "c1", "m1"))
    assert bus.has_pending_outbound("chat", "c1", "m1") is True


def test_interrupt_controller_preserves_complete_transport_scope() -> None:
    controller = FakeInterruptController()
    controller.request_interrupt(
        "role:mira",
        channel="telegram_one",
        chat_id="room",
        sender="alice",
        account_id="telegram:one",
        chat_type="supergroup",
        message_thread_id="11",
    )
    assert controller.requests == [
        {
            "session_key": "role:mira",
            "channel": "telegram_one",
            "chat_id": "room",
            "sender": "alice",
            "command": "/stop",
            "account_id": "telegram:one",
            "chat_type": "supergroup",
            "message_thread_id": "11",
        }
    ]
