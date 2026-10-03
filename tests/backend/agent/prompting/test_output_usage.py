"""Visible output accounting never treats malformed or hidden reasoning as text."""

from types import SimpleNamespace
import pytest
from agent.prompting.output_usage import parse_output_usage


@pytest.mark.parametrize("container", [dict, SimpleNamespace])
@pytest.mark.parametrize(
    "completion,reasoning,thinking,expected,reason",
    [
        (1392, None, False, 1392, ""),
        (7000, 5608, True, 1392, ""),
        (7000, 5608, False, 1392, ""),
        (7000, None, True, None, "missing_reasoning_usage"),
        (7000, -1, False, None, "invalid_reasoning_usage"),
        (7000, 7001, False, None, "invalid_reasoning_usage"),
        (7000, 7000, False, None, "invalid_reasoning_usage"),
        (7000, True, False, None, "invalid_reasoning_usage"),
        (7000, "5608", False, None, "invalid_reasoning_usage"),
        (None, None, False, None, "missing_completion_usage"),
        (0, None, False, None, "invalid_completion_usage"),
        (-1, None, False, None, "invalid_completion_usage"),
        (True, None, False, None, "invalid_completion_usage"),
        (1392.5, None, False, None, "invalid_completion_usage"),
        ("1392", None, False, None, "invalid_completion_usage"),
    ],
)
def test_only_usable_visible_counts_are_available(
    container, completion, reasoning, thinking, expected, reason
):
    result = parse_output_usage(
        container(
            completion_tokens=completion,
            completion_tokens_details=container(reasoning_tokens=reasoning),
        ),
        has_thinking=thinking,
    )
    assert result.visible_tokens == expected
    assert result.unavailable_reason == reason
