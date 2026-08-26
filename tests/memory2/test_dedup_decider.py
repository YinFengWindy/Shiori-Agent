from __future__ import annotations

import asyncio
from types import SimpleNamespace

from memory2.dedup_decider import DedupDecision, DedupDecider, MemoryAction


def _decider() -> DedupDecider:
    return DedupDecider.__new__(DedupDecider)


def _similar() -> list[dict[str, str]]:
    return [
        {"id": "mem-1", "summary": "old one"},
        {"id": "mem-2", "summary": "old two"},
    ]


def test_legacy_merge_decision_repairs_to_first_target() -> None:
    decision, reason, actions, codes = _decider()._parse_payload(
        {"decision": "merge", "list": []}, _similar()
    )

    assert decision is DedupDecision.NONE
    assert actions[0].item_id == "mem-1"
    assert actions[0].action is MemoryAction.MERGE
    assert "legacy_decision_merge" in codes
    assert "invalid" not in reason


def test_legacy_one_based_index_is_repaired() -> None:
    decision, _, actions, codes = _decider()._parse_payload(
        {"decision": "none", "list": [{"index": 2, "decide": "merge"}]},
        _similar(),
    )

    assert decision is DedupDecision.NONE
    assert actions[0].item_id == "mem-2"
    assert "legacy_index_1_based" in codes


def test_unknown_id_conservatively_skips() -> None:
    decision, _, actions, codes = _decider()._parse_payload(
        {"decision": "create", "list": [{"id": "missing", "decide": "delete"}]},
        _similar(),
    )

    assert decision is DedupDecision.SKIP
    assert actions == []
    assert "invalid_unknown_id" in codes


def test_missing_decision_or_non_list_actions_skip() -> None:
    missing_decision, _, _, missing_codes = _decider()._parse_payload(
        {"list": []}, _similar()
    )
    bad_list, _, _, bad_list_codes = _decider()._parse_payload(
        {"decision": "create", "list": {"id": "mem-1"}}, _similar()
    )

    assert missing_decision is DedupDecision.SKIP
    assert "invalid_missing_decision" in missing_codes
    assert bad_list is DedupDecision.SKIP
    assert "invalid_action_list" in bad_list_codes


def test_unknown_index_zero_is_not_treated_as_zero_based() -> None:
    decision, _, actions, codes = _decider()._parse_payload(
        {"decision": "none", "list": [{"index": 0, "decide": "merge"}]},
        _similar(),
    )

    assert decision is DedupDecision.SKIP
    assert actions == []
    assert "invalid_unknown_index" in codes


def test_conflicting_actions_skip_entire_payload() -> None:
    decision, _, actions, codes = _decider()._parse_payload(
        {
            "decision": "none",
            "list": [
                {"id": "mem-1", "decide": "merge"},
                {"id": "mem-1", "decide": "delete"},
            ],
        },
        _similar(),
    )

    assert decision is DedupDecision.SKIP
    assert actions == []
    assert "invalid_conflicting_actions" in codes


def test_multi_merge_and_missing_merge_target_skip() -> None:
    multi_decision, _, _, multi_codes = _decider()._parse_payload(
        {
            "decision": "none",
            "list": [
                {"id": "mem-1", "decide": "merge"},
                {"id": "mem-2", "decide": "merge"},
            ],
        },
        _similar(),
    )
    missing_decision, _, _, missing_codes = _decider()._parse_payload(
        {"decision": "none", "list": []}, _similar()
    )

    assert multi_decision is DedupDecision.SKIP
    assert "invalid_multi_merge" in multi_codes
    assert missing_decision is DedupDecision.SKIP
    assert "invalid_missing_merge_target" in missing_codes


def test_provider_and_json_failures_keep_distinct_reason_codes() -> None:
    class FailingProvider:
        async def chat(self, **_: object) -> object:
            raise RuntimeError("offline")

    class JsonProvider:
        async def chat(self, **_: object) -> object:
            return SimpleNamespace(content="not json")

    async def run() -> tuple[tuple[DedupDecision, str, list, tuple[str, ...]], tuple[DedupDecision, str, list, tuple[str, ...]]]:
        first = _decider()
        first._provider = FailingProvider()
        first._model = "test"
        second = _decider()
        second._provider = JsonProvider()
        second._model = "test"
        return await first._llm_decide("candidate", _similar()), await second._llm_decide(
            "candidate", _similar()
        )

    provider_result, json_result = asyncio.run(run())
    assert provider_result[0] is DedupDecision.CREATE
    assert provider_result[3] == ("provider_error",)
    assert json_result[0] is DedupDecision.CREATE
    assert json_result[3] == ("json_parse_error",)
