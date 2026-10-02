"""Channel service fakes keep the host's ownership and reply rules."""

from shiori_sdk.messages import OutboundMessage
from shiori_sdk.testing.channel_services import (
    FakeInterruptController,
    FakeMessageBus,
    FakePushSenders,
)


async def _text(chat_id: str, text: str) -> str | None:
    return None


async def _other_text(chat_id: str, text: str) -> str | None:
    return None


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


def test_push_senders_record_offered_senders_and_keep_a_replacement() -> None:
    senders = FakePushSenders()
    senders.register_channel("chat", text=_text, image=_text, description=" 说明 ")
    assert senders.registrations == {
        "chat": {"text": _text, "image": _text, "description": "说明"}
    }

    senders.register_channel("chat", text=_other_text)
    # The old connection stopping must not remove its replacement.
    senders.unregister_channel("chat", text=_text)
    assert senders.registrations == {"chat": {"text": _other_text}}
    senders.unregister_channel("chat", text=_other_text)
    assert senders.registrations == {} and senders.senders == {}


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
