"""Closed tool exchanges retain result evidence without replayable protocol rows."""

import pytest

from agent.core.passive_turn.minimal_request import (
    completed_tool_results,
    current_input,
    replace_current_input,
)


def test_complete_tool_results_preserve_media_and_drop_arguments_and_reasoning():
    attachment = {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,abc"},
    }
    messages = [
        {
            "role": "assistant",
            "content": "planning",
            "reasoning_content": "private",
            "tool_calls": [
                {"id": "a", "function": {"name": "write", "arguments": "large args"}}
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "a",
            "content": [attachment, {"type": "text", "text": "written once"}],
        },
    ]
    result = completed_tool_results(messages)
    assert len(result) == 1 and result[0]["content"][1] == attachment
    assert "written once" in str(result)
    assert "large args" not in str(result) and "private" not in str(result)
    assert messages[0]["tool_calls"]


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "tool", "tool_call_id": "missing", "content": "orphan"}],
        [
            {
                "role": "assistant",
                "tool_calls": [{"id": "a", "function": {"name": "write"}}],
            }
        ],
    ],
)
def test_open_or_orphaned_tools_fail_without_silent_loss(messages):
    with pytest.raises(ValueError):
        completed_tool_results(messages)


def test_owned_current_input_wins_over_identical_history_and_trailing_hint():
    old = {"role": "user", "content": "same"}
    owned = dict(old)
    hint = {"role": "user", "content": "<system-reminder>optional</system-reminder>"}
    assert current_input([old, owned, hint], owned) is owned
    assert current_input([old, owned, hint]) is owned


def test_replacing_current_input_uses_identity_and_copies_nested_attachments():
    old = {"role": "user", "content": "same"}
    owned = dict(old)
    hint = {"role": "user", "content": "<system-reminder>optional</system-reminder>"}
    frozen = {
        "role": "user",
        "content": [{"type": "image_url", "image_url": {"url": "original.png"}}],
    }
    messages = [old, owned, hint]
    replace_current_input(messages, frozen, owned)
    assert messages[0] is old and messages[2] is hint
    assert messages[1] == frozen and messages[1] is not frozen
    frozen["content"][0]["image_url"]["url"] = "changed.png"
    assert messages[1]["content"][0]["image_url"]["url"] == "original.png"
