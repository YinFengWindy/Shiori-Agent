from bus.events_lifecycle import TurnCommitted
from desktop_bridge.turn_messages import committed_turn_messages
from session.manager import Session


def test_committed_rows_use_identity_instead_of_matching_repeated_reply_text():
    session = Session(key="role:mira")
    for message_id, role in [
        ("old", "assistant"),
        ("user", "user"),
        ("push", "assistant"),
        ("final", "assistant"),
    ]:
        session.add_message(role, "same text", id=message_id)
    event = TurnCommitted(
        session_key=session.key,
        channel="qqbot",
        chat_id="friend",
        input_message="same text",
        persisted_user_message="same text",
        assistant_response="same text",
        tools_used=[],
        extra={"committed_message_ids": ["user", "push", "final"]},
    )
    assert committed_turn_messages(session, event) == session.messages[1:]
    assert committed_turn_messages(session, None) is None
