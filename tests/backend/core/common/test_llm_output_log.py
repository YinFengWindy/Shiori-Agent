"""Shared raw-LLM-output logging helper.

Backs the raw-output logging in `agent.provider` (tool-call argument parse
failures), `agent.core.reply_completion.fetch_role_mood` (truncated/malformed
mood responses), and `agent.core.response_parser` (malformed structured
replies) - see issue #304. Exercised directly here so the truncation and
redaction rules are proven once, independent of any of those call sites.

Redaction cases below are organised by credential *shape*, not by
implementation, per the #304 two-axis review: the original patterns were
written to pass whatever tests already existed rather than against a list of
how a credential can actually appear in text, and missed the JSON-quoted
form entirely - which is this helper's dominant real shape, since its main
caller (`fetch_role_mood`) always requests
`response_format={"type": "json_object"}`.
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


# --- credential shape: JSON-quoted key/value (the dominant real shape) ---


def test_redacts_json_quoted_api_key() -> None:
    """Exact case the previous patterns missed: reported by the #304
    two-axis review as leaking the credential verbatim."""
    result = summarize_llm_output_for_log(
        '{"mood":"平静","api_key": "AIzaSyAbc123Def456"}'
    )

    assert "AIzaSyAbc123Def456" not in result
    assert "REDACTED" in result
    # The surrounding JSON structure and unrelated fields must survive.
    assert '"mood":"平静"' in result
    assert '"api_key"' in result


def test_redacts_json_quoted_access_token() -> None:
    result = summarize_llm_output_for_log(
        '{"access_token": "ya29.aVeryLongTokenValue"}'
    )

    assert "ya29.aVeryLongTokenValue" not in result
    assert "REDACTED" in result


def test_json_quoted_redaction_caps_value_length() -> None:
    """A JSON-quoted value longer than the cap must still be fully replaced
    (not partially redacted, leaking the tail)."""
    huge = "a" * 500
    result = summarize_llm_output_for_log(f'{{"secret": "{huge}"}}')

    assert huge not in result
    assert "REDACTED" in result


# --- credential shape: bare key=value / key: value ---


def test_redacts_bare_key_equals_value() -> None:
    result = summarize_llm_output_for_log("api_key=AIzaSyAbc123Def456")

    assert "AIzaSyAbc123Def456" not in result
    assert "REDACTED" in result


def test_redacts_bare_key_colon_value() -> None:
    result = summarize_llm_output_for_log("api_key: AIzaSyAbc123Def456")

    assert "AIzaSyAbc123Def456" not in result
    assert "REDACTED" in result


def test_redacts_spaced_key_name_written_as_prose() -> None:
    """A model echoing a credential in prose writes "api key: ..." as readily
    as "api_key=..."; the spaced key name leaked past an earlier version of
    this pattern, so it stays pinned here."""
    result = summarize_llm_output_for_log("api key: AIzaSyAbc123Def456")

    assert "AIzaSyAbc123Def456" not in result
    assert "REDACTED" in result


def test_spaced_key_name_alone_is_not_treated_as_a_credential() -> None:
    """Widening the key separator must not start redacting ordinary dialogue
    that merely mentions the words."""
    dialogue = "这个 api key 的事我们改天聊"

    assert summarize_llm_output_for_log(dialogue) == dialogue


def test_bare_key_value_redaction_stops_at_word_boundary() -> None:
    """The value capture must not run past the credential into unrelated
    trailing text once it hits a separator (comma here)."""
    result = summarize_llm_output_for_log("api_key=AIzaSyAbc123Def456,后面是正常对白")

    assert "AIzaSyAbc123Def456" not in result
    assert "后面是正常对白" in result


# --- credential shape: sk-... prefixed keys ---


def test_redacts_sk_prefixed_key() -> None:
    leaked = "sk-" + "a" * 40
    result = summarize_llm_output_for_log(f"here is my key {leaked} use it")

    assert leaked not in result
    assert "REDACTED" in result


# --- credential shape: Bearer tokens ---


def test_redacts_bearer_token_fully_not_just_the_word_bearer() -> None:
    """Regression guard for the ordering bug the #304 review flagged: if the
    generic bare key/value pattern ran before the Bearer-specific one, it
    would redact only the word "Bearer" (6 chars, its own valid "value")
    and leave the actual token exposed right after it."""
    result = summarize_llm_output_for_log("Authorization: Bearer abcdef1234567890")

    assert "abcdef1234567890" not in result
    assert "REDACTED" in result


# --- additional key names required by the #304 review ---


def test_redacts_labelled_password() -> None:
    result = summarize_llm_output_for_log("password=hunter2isnotreallyit")

    assert "hunter2isnotreallyit" not in result
    assert "REDACTED" in result


def test_redacts_labelled_authorization_header_style_value() -> None:
    result = summarize_llm_output_for_log('{"authorization": "Basic dXNlcjpwYXNz"}')

    assert "dXNlcjpwYXNz" not in result
    assert "REDACTED" in result


def test_redacts_bare_token_key() -> None:
    result = summarize_llm_output_for_log("token=abcdef1234567890xyz")

    assert "abcdef1234567890xyz" not in result
    assert "REDACTED" in result


# --- must not over-match ordinary text ---


def test_does_not_redact_plain_dialogue_without_credential_shape() -> None:
    text = "她说：稍等一下，这不是什么密码。"
    assert summarize_llm_output_for_log(text) == text
