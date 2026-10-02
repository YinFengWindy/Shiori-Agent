"""Host projection of admitted input is a pure, shared function."""

from shiori_sdk.channels.message_source import SENDER_IS_USER_KEY
from shiori_sdk.channels.projection import plugin_metadata, project_inbound
from shiori_sdk.messages import InboundMessage


def test_plugin_metadata_drops_flags_only_the_host_may_assert() -> None:
    message = InboundMessage(
        "chat", "u", "c", "hi", metadata={SENDER_IS_USER_KEY: True, "k": 1}
    )

    assert plugin_metadata(message) == {"k": 1}
    assert message.metadata[SENDER_IS_USER_KEY] is True


def test_projection_keeps_context_and_chat_type_set_by_the_plugin() -> None:
    message = InboundMessage("chat", "u", "c", "hi", media=["a.png"])
    metadata = {"chat_type": "group", "context_chat_id": "other", "source": "x"}

    routed = project_inbound(
        message,
        metadata,
        role_id="mira",
        thread_id="t1",
        session_key="role:mira",
        default_chat_type="private",
    )

    assert routed.metadata["chat_type"] == "group"
    assert routed.metadata["context_chat_id"] == "other"
    assert routed.metadata["source"] == "x"
    assert routed.metadata["thread_id"] == "t1"
    assert "external_message_id" not in routed.metadata
    assert routed.media == ["a.png"] and routed.media is not message.media
    assert metadata == {"chat_type": "group", "context_chat_id": "other", "source": "x"}
