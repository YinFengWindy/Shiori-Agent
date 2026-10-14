"""User-turn side effects must not treat a synthetic result as fresh user input."""

from agent.lifecycle.types import TurnState
from shiori_sdk.messages import InboundMessage


def test_background_report_is_not_a_new_user_turn():
    message = InboundMessage(
        channel="desktop",
        chat_id="role:mira",
        sender="user",
        content="result",
        metadata={"source": "background_result"},
    )
    state = TurnState(message, "role:mira", True)
    assert state.is_user_authored()
    assert not state.is_user_turn()
    message.metadata["source"] = "desktop"
    assert state.is_user_turn()
