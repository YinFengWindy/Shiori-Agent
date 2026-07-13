from bus.events import OutboundMessage
from infra.channels.session_key import resolve_outbound_session_key


def test_resolve_outbound_session_key_prefers_role_runtime_key() -> None:
    message = OutboundMessage(
        channel="telegram",
        chat_id="42",
        content="reply",
        metadata={
            "session_key_override": "role:mira",
            "role_id": "mira",
        },
    )

    assert resolve_outbound_session_key(message, default_channel="telegram") == (
        "role:mira"
    )


def test_resolve_outbound_session_key_does_not_use_thread_runtime_key() -> None:
    message = OutboundMessage(
        channel="telegram",
        chat_id="42",
        content="reply",
        metadata={"session_key_override": "thread:mira:telegram:42"},
    )

    assert resolve_outbound_session_key(message, default_channel="telegram") == (
        "telegram:42"
    )


def test_resolve_outbound_session_key_falls_back_to_transport_session() -> None:
    message = OutboundMessage(channel="qq", chat_id="42", content="reply")

    assert resolve_outbound_session_key(message, default_channel="qq") == "qq:42"
