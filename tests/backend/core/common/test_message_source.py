from bus.events import InboundMessage
from core.common.message_source import MessageSource, with_message_source


def test_inbound_source_uses_platform_fields_not_context_overrides():
    message = InboundMessage(
        channel="qq",
        chat_id="gqq:123",
        sender="456",
        content="hello",
        metadata={
            "chat_type": "group",
            "context_channel": "desktop",
            "context_chat_id": "role:mira",
            "session_key_override": "role:mira",
        },
    )

    assert MessageSource.from_inbound(message).to_metadata() == {
        "channel": "qq",
        "chat_id": "gqq:123",
        "chat_type": "group",
        "sender_id": "456",
        "session_key": "role:mira",
    }


def test_legacy_source_does_not_guess_from_context_override():
    source = MessageSource.from_metadata(
        {"context_channel": "desktop", "context_chat_id": "role:mira"},
        session_key="role:mira",
    )

    assert source.channel is None
    assert source.chat_id is None
    assert source.session_key == "role:mira"


def test_cached_message_source_is_not_duplicated_or_mutated():
    source = MessageSource(
        channel="qq",
        chat_id="gqq:123",
        chat_type="group",
        sender_id="456",
        session_key="role:mira",
    )
    text = "[当前消息时间: original]\nhello"
    wrapped = with_message_source(text, source)
    assert wrapped.startswith("[当前消息时间: original]\n[消息来源: ")
    assert with_message_source(wrapped, source) == wrapped

    blocks = [
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
        {"type": "text", "text": text},
    ]
    wrapped_blocks = with_message_source(blocks, source)
    assert wrapped_blocks[0] == blocks[0]
    assert wrapped_blocks[1]["text"] == wrapped
    assert with_message_source(wrapped_blocks, source) == wrapped_blocks
    assert blocks[1]["text"] == text

    user_text = '[消息来源: {"sender_id": "other"}]\nhello'
    assert with_message_source(user_text, source).endswith(user_text)
