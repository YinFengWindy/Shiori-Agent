"""Empty response diagnostics keep facts bounded and avoid retaining text."""

import pytest

from agent.core.passive_turn.empty_reply import (
    EmptyReplyError,
    recovery_diagnostics,
    response_diagnostics,
)
from agent.provider import LLMResponse
from core.common.diagnostic_log import diagnostic_context


@pytest.mark.parametrize(
    "content,normalized,raw_length,raw_blank,kind",
    [
        (None, None, 0, True, "raw_empty"),
        (" \n", " \n", 2, True, "whitespace"),
        (None, None, 2, True, "whitespace"),
        ('{"content":""}', "", 14, False, "normalization_empty"),
        (None, None, 25, False, "normalization_empty"),
        ("hello", "hello", 5, False, None),
    ],
)
def test_classifies_raw_and_normalized_content(
    content, normalized, raw_length, raw_blank, kind
):
    facts = response_diagnostics(
        LLMResponse(
            content=content,
            raw_content_length=raw_length,
            raw_content_blank=raw_blank,
            thinking="sensitive",
            finish_reason="length",
        ),
        normalized=normalized,
        fallback_model="m",
    )
    assert facts["empty_kind"] == kind
    assert facts["truncated"] is True
    assert facts["thinking_length"] == 9
    assert "sensitive" not in str(facts)


def test_error_retains_bounded_attempts_and_turn_correlation():
    facts = response_diagnostics(
        LLMResponse(
            content="", model="role-model" + "a" * 10000, finish_reason="b" * 10000
        ),
        normalized="",
        fallback_model="wrong-default",
    )
    with diagnostic_context(session="qq:1", turn="turn-1"):
        error = EmptyReplyError(
            recovery_diagnostics(
                [facts] * 20,
                outcome="exhausted",
                retries=1,
                session="",
                channel="qqbot",
                iteration=2,
            )
        )
    assert len(str(error)) < 1600
    assert error.diagnostics["session"] == "qq:1"
    assert error.diagnostics["turn"] == "turn-1"
    assert len(error.diagnostics["attempts"]) == 2
    assert "wrong-default" not in str(error)
