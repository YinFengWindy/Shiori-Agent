"""Origin metadata stays isolated from caller mutations after capture."""

from agent.tools.turn_origin import current_tool_origin, set_tool_origin
from shiori_sdk.messages import InboundMessage


def test_original_channel_metadata_is_copied_at_capture_and_read():
    message = InboundMessage(
        channel="telegram:account",
        chat_id="chat",
        sender="user",
        content="task",
        metadata={"message_thread_id": 27, "nested": {"account": "original"}},
    )
    set_tool_origin(message)
    message.metadata["nested"]["account"] = "mutated"
    origin = current_tool_origin()
    assert origin.metadata["nested"]["account"] == "original"
    origin.metadata["message_thread_id"] = 88
    assert current_tool_origin().metadata["message_thread_id"] == 27
