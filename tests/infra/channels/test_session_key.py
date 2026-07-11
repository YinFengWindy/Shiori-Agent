from bus.events import OutboundMessage
from infra.channels.session_key import resolve_outbound_session_key


def test_resolve_outbound_session_key_prefers_thread_runtime_key() -> None:
    message = OutboundMessage(
        channel="telegram",
        chat_id="42",
        content="reply",
        metadata={"session_key_override": "thread:mira:telegram:42"},
    )

    assert resolve_outbound_session_key(message, default_channel="telegram") == (
        "thread:mira:telegram:42"
    )


def test_resolve_outbound_session_key_falls_back_to_transport_session() -> None:
    message = OutboundMessage(channel="qq", chat_id="42", content="reply")

    assert resolve_outbound_session_key(message, default_channel="qq") == "qq:42"
