from __future__ import annotations

from core.common.error_summary import summarize_exception_for_user


class ProviderError(Exception):
    pass


def test_summary_is_type_and_first_line_only() -> None:
    exc = ProviderError(
        "upstream returned 502\nTraceback (most recent call last):\n  x"
    )

    assert summarize_exception_for_user(exc) == "ProviderError: upstream returned 502"


def test_summary_without_message_is_the_type_name() -> None:
    assert summarize_exception_for_user(TimeoutError()) == "TimeoutError"


def test_summary_scrubs_bearer_tokens_and_api_keys() -> None:
    exc = RuntimeError(
        "401 for Authorization: Bearer abcdefghijklmnop api_key=sk-live-123456789012"
        " at https://example.com/v1?key=AIzaSyDUMMYDUMMY&alt=json"
    )

    summary = summarize_exception_for_user(exc)

    assert "abcdefghijklmnop" not in summary
    assert "123456789012" not in summary
    assert "AIzaSyDUMMYDUMMY" not in summary
    assert "alt=json" in summary
    assert summary.startswith("RuntimeError: 401 for Authorization: ")


def test_summary_is_capped() -> None:
    summary = summarize_exception_for_user(ValueError("x" * 1000))

    assert len(summary) == 300
    assert summary.endswith("…")
