"""Lifecycle retention treats tools and interrupted inputs as complete units."""

import pytest
from session.turns import retention_stop


def _message(role, **kwargs):
    return {"role": role, "content": role, **kwargs}


@pytest.mark.parametrize("keep,expected", [(2, 0), (1, 2), (0, 4)])
def test_retains_completed_turns_and_current_input(keep, expected):
    messages = [
        _message("user"),
        _message("assistant"),
        _message("user"),
        _message("assistant"),
        _message("user", media=["current.png"]),
    ]
    assert retention_stop(messages, list(range(5)), keep) == (expected, keep)


def test_native_calls_wait_for_results_and_final_reply_before_starting_a_new_turn():
    messages = [
        _message("user"),
        _message("assistant", tool_calls=[{"id": "one"}]),
        _message("user"),
        _message("assistant"),
        _message("tool", tool_call_id="one"),
        _message("assistant"),
        _message("user"),
    ]
    assert retention_stop(messages, list(range(7)), 0) == (6, 0)
    assert retention_stop(messages[:4], list(range(4)), 0) == (0, 0)


def test_consecutive_users_and_interrupted_reply_are_one_lifecycle():
    messages = [
        _message("user"),
        _message("assistant", metadata={"interrupted_turn": True}),
        _message("user"),
        _message("assistant"),
        _message("user"),
        _message("assistant"),
    ]
    assert retention_stop(messages, list(range(6)), 1) == (4, 1)


def test_interleaved_thread_members_and_embedded_tool_chain_preserve_boundary():
    messages = [
        _message("user"),
        _message("user"),
        _message("assistant", tool_chain=[{"calls": [{"id": "one"}]}]),
        _message("assistant"),
        _message("user"),
        _message("assistant"),
    ]
    assert retention_stop(messages, [0, 2, 4, 5], 1) == (4, 1)
