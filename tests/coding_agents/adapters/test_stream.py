from __future__ import annotations

import pytest

from coding_agents.adapters.base import AdapterError
from coding_agents.adapters.stream import (
    decode_json_line,
    parse_claude_event,
    parse_codex_event,
)


def test_decode_json_line_rejects_malformed_provider_output() -> None:
    with pytest.raises(AdapterError) as raised:
        decode_json_line(b"{not-json}\n")

    assert raised.value.code == "unsupported_capability"


def test_codex_event_maps_session_tools_and_assistant_output() -> None:
    started = parse_codex_event(
        {"type": "thread.started", "thread_id": "session-1"}
    )
    tool = parse_codex_event(
        {
            "type": "item.completed",
            "item": {
                "id": "item-1",
                "type": "command_execution",
                "command": "pytest",
                "status": "completed",
            },
        }
    )
    message = parse_codex_event(
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "完成"},
        }
    )

    assert started[0].payload["session_id"] == "session-1"
    assert tool[0].event_type == "tool_finished"
    assert message[0].payload["text"] == "完成"


def test_claude_partial_and_tool_result_events_are_mapped() -> None:
    delta = parse_claude_event(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "一部分"},
            },
        }
    )
    finished = parse_claude_event(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool-1"}
                ]
            },
        }
    )

    assert delta[0].event_type == "assistant_delta"
    assert delta[0].payload["text"] == "一部分"
    assert finished[0].event_type == "tool_finished"
