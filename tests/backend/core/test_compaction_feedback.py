"""Manual failures present their stage without leaking parser/provider diagnostics."""

import json

from core.compaction import CompactionResult
from core.compaction_feedback import compaction_feedback


def test_parser_failure_is_a_readable_summary_with_scrubbed_detail():
    error = json.JSONDecodeError("Expecting value token=private-value", "", 0)
    result = compaction_feedback(
        CompactionResult(
            failure_stage="summary",
            memory_committed=True,
            error=str(error),
        ),
        error,
    )
    assert result["memory_committed"]
    assert result["error"] == "工作摘要生成失败，请稍后重试"
    assert "JSONDecodeError: Expecting value" in result["detail"]
    assert "private-value" not in result["detail"]


def test_budget_reduction_has_one_wording_for_every_surface():
    reduced = CompactionResult(
        committed=True,
        configured_retained_turns=2,
        retained_turns=1,
        retained_reduction_reason="budget",
    )
    assert (
        compaction_feedback(reduced)["reduction"]
        == "保留 2 个轮次会超出预算，本次保留 1 个"
    )
    kept = CompactionResult(
        committed=True, configured_retained_turns=2, retained_turns=2
    )
    assert compaction_feedback(kept)["reduction"] == ""
