"""Host raw-LLM-output logging helper.

Backs the raw-output logging in `agent.provider` (tool-call argument parse
failures), `agent.core.reply_completion.fetch_role_mood` (truncated/malformed
mood responses), and `agent.core.response_parser` (malformed structured
replies) - see issue #304. Credential shapes are covered by the SDK's
`redact_secrets` tests; here only the log rendering rules are pinned.
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


def test_summarize_llm_output_for_log_redacts_before_logging() -> None:
    result = summarize_llm_output_for_log(
        '{"mood":"平静","api_key": "AIzaSyAbc123Def456"}'
    )

    assert "AIzaSyAbc123Def456" not in result
    assert '"mood":"平静"' in result
