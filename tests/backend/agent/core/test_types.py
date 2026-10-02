from __future__ import annotations

from agent.core.types import HistoryMessage, to_tool_call_groups
from shiori_sdk.tool_chain import ToolCall, ToolCallGroup


def test_to_tool_call_groups_returns_empty_list_for_empty_chain():
    assert to_tool_call_groups([]) == []


def test_to_tool_call_groups_converts_raw_dicts_to_dataclasses():
    raw = [
        {
            "text": "I'll call shell",
            "calls": [
                {
                    "call_id": "c1",
                    "name": "shell",
                    "arguments": {"cmd": "ls"},
                    "result": "ok",
                },
            ],
        }
    ]

    groups = to_tool_call_groups(raw)

    assert len(groups) == 1
    assert isinstance(groups[0], ToolCallGroup)
    assert groups[0].text == "I'll call shell"
    assert len(groups[0].calls) == 1
    call = groups[0].calls[0]
    assert isinstance(call, ToolCall)
    assert call.name == "shell"
    assert call.arguments == {"cmd": "ls"}
    assert call.result == "ok"


def test_to_tool_call_groups_coerces_non_dict_arguments_to_empty_dict():
    raw = [
        {
            "text": "",
            "calls": [{"call_id": "c1", "name": "x", "arguments": "bad", "result": ""}],
        }
    ]

    groups = to_tool_call_groups(raw)

    assert groups[0].calls[0].arguments == {}


def test_history_message_defaults_tool_chain_to_empty_list():
    msg = HistoryMessage(role="user", content="hello", tools_used=["shell"])

    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.tools_used == ["shell"]
    assert msg.tool_chain == []
