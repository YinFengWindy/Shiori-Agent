"""Working-summary limits apply to normalized content and auditable count sources."""

import json
import pytest
from agent.prompting.output_usage import parse_output_usage
from agent.prompting.token_estimate import estimate_tokens
from core.compaction_summary_validation import (
    SUMMARY_FIELDS,
    SummaryTooLong,
    normalize_summary,
    summary_attempt,
    validate_summary_limit,
)


def _state(**changes):
    return json.dumps(
        dict.fromkeys(SUMMARY_FIELDS, "") | {"source_message_ids": ["old"]} | changes,
        ensure_ascii=False,
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2000", None])
def test_limit_rejects_non_positive_integer(value):
    with pytest.raises(ValueError, match="正整数"):
        validate_summary_limit(value)


def test_exact_local_limit_and_deduplicated_ids_are_measured_before_storage():
    text = _state(source_message_ids=["old"] * 2000)
    canonical = json.dumps(
        json.loads(_state()), ensure_ascii=False, separators=(",", ":")
    )
    limit = estimate_tokens(canonical)
    result = normalize_summary(text, {"old"}, summary_attempt(limit, None))
    assert result.content == canonical
    assert result.source_ids == ("old",)
    assert result.diagnostics[0].counted_tokens == limit
    assert result.diagnostics[0].source_count == 1
    with pytest.raises(SummaryTooLong):
        normalize_summary(text, {"old"}, summary_attempt(limit - 1, None))


@pytest.mark.parametrize(
    "changes",
    [
        {"metadata": "private" * 3000},
        {"source_message_ids": ["old"] * 2000},
    ],
)
def test_raw_usage_does_not_charge_discarded_projection(changes):
    usage = parse_output_usage({"completion_tokens": 8000})
    result = normalize_summary(_state(**changes), {"old"}, summary_attempt(2000, usage))
    count = result.diagnostics[0]
    assert count.provider_output_tokens == 8000
    assert count.counted_tokens == count.local_tokens < 2000
    assert count.source == "local_normalized_estimate"
    assert count.fallback_reason == "normalized_projection"
    assert "private" not in result.content


def test_whitespace_does_not_discard_an_oversized_provider_count():
    text = json.dumps(json.loads(_state()), indent=4)
    with pytest.raises(SummaryTooLong) as error:
        normalize_summary(
            text,
            {"old"},
            summary_attempt(2000, parse_output_usage({"completion_tokens": 2100})),
        )
    assert error.value.diagnostics[0].source == "provider_output_upper_bound"


def test_valid_provider_upper_bound_accepts_chinese_despite_conservative_local_estimate():
    result = normalize_summary(
        _state(tasks="中" * 1100),
        {"old"},
        summary_attempt(2000, parse_output_usage({"completion_tokens": 1392})),
    )
    count = result.diagnostics[0]
    assert count.local_tokens > 2000
    assert count.counted_tokens == 1392
    assert count.source == "provider_output_upper_bound"
