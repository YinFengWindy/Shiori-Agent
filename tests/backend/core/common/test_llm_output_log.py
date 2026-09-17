"""Shared raw-LLM-output logging helper.

Backs the raw-output logging in `agent.provider` (tool-call argument parse
failures), `agent.core.reply_completion.fetch_role_mood` (truncated/malformed
mood responses), and `agent.core.response_parser` (malformed structured
replies) - see issue #304. Exercised directly here so the truncation and
redaction rules are proven once, independent of any of those call sites.
"""

from core.common.llm_output_log import summarize_llm_output_for_log


def test_summarize_llm_output_for_log_returns_short_text_unchanged() -> None:
    assert summarize_llm_output_for_log("hello") == "hello"


def test_summarize_llm_output_for_log_marks_empty_content() -> None:
    assert summarize_llm_output_for_log(None) == "<empty>"
    assert summarize_llm_output_for_log("") == "<empty>"


def test_summarize_llm_output_for_log_caps_length_with_suffix() -> None:
    text = "x" * 600
    result = summarize_llm_output_for_log(text, limit=500)

    assert result.startswith("x" * 500)
    assert result == "x" * 500 + "...(+100 chars)"


def test_summarize_llm_output_for_log_redacts_openai_style_key() -> None:
    leaked = "sk-" + "a" * 40
    result = summarize_llm_output_for_log(f"here is my key {leaked} use it")

    assert leaked not in result
    assert "REDACTED" in result


def test_summarize_llm_output_for_log_redacts_bearer_token() -> None:
    result = summarize_llm_output_for_log("Authorization: Bearer abcdef1234567890")

    assert "abcdef1234567890" not in result
    assert "REDACTED" in result


def test_summarize_llm_output_for_log_redacts_labelled_api_key() -> None:
    result = summarize_llm_output_for_log("api_key=super-secret-value-123456789")

    assert "super-secret-value-123456789" not in result
    assert "REDACTED" in result
