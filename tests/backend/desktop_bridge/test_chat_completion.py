from bus.events_lifecycle import TurnCommitted
from desktop_bridge.chat_completion import build_chat_terminal_event


def test_uncommitted_empty_reply_has_a_visible_error():
    event = build_chat_terminal_event(
        request_id="request-1",
        turn_id="turn-1",
        session_key="role:mira",
        role_id="mira",
    )

    assert event.method == "chat.error"
    assert event.payload == {
        "session_key": "role:mira",
        "turn_id": "turn-1",
        "message": "回合未完成，请重试。",
    }


def test_committed_empty_reply_is_still_a_successful_turn():
    event = build_chat_terminal_event(
        request_id="request-1",
        turn_id="turn-1",
        session_key="role:mira",
        role_id="mira",
        committed=TurnCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            input_message="hello",
            persisted_user_message=None,
            assistant_response="",
            tools_used=["message_push"],
            total_tokens=120,
        ),
    )

    assert event.method == "chat.done"
    assert event.payload["reply"] == ""
    assert event.payload["tools_used"] == ["message_push"]
    assert event.payload["total_tokens"] == 120


def test_uncommitted_turn_carries_a_failure_detail_when_known():
    event = build_chat_terminal_event(
        request_id="request-1",
        turn_id="turn-1",
        session_key="role:mira",
        role_id="mira",
        failure_message="处理消息时出错，请稍后再试。",
        failure_detail="APIConnectionError: Connection error.",
    )

    assert event.method == "chat.error"
    assert event.payload["message"] == "处理消息时出错，请稍后再试。"
    assert event.payload["detail"] == "APIConnectionError: Connection error."
