from types import SimpleNamespace

from agent.prompting.usage_accounting import current_usage, record_usage, turn_usage


def test_usage_keeps_unknown_fields_per_call_and_marks_partial_totals():
    with turn_usage():
        record_usage(
            SimpleNamespace(
                model="m",
                prompt_tokens=120,
                completion_tokens=10,
                cache_hit_tokens=None,
                total_tokens=130,
                input_budget=None,
            ),
            purpose="default",
        )
        record_usage(
            SimpleNamespace(
                model="m",
                prompt_tokens=None,
                completion_tokens=None,
                cache_hit_tokens=None,
                total_tokens=None,
                input_budget=None,
            ),
            purpose="auxiliary",
        )
        report = current_usage()
        assert report["last_request"]["prompt_tokens"] == 120
        assert report["cumulative"]["prompt_tokens"] == 120
        assert report["cumulative"]["prompt_tokens_unknown_calls"] == 1
        assert report["cumulative"]["cache_hit_tokens"] is None
        assert report["cumulative"]["cache_hit_tokens_unknown_calls"] == 2
        assert report["calls"][1]["prompt_tokens"] is None
    assert current_usage()["calls"] == []


def test_failed_request_does_not_inherit_previous_actual_usage():
    from agent.prompting.usage_accounting import record_failed_usage

    with turn_usage():
        record_usage(
            SimpleNamespace(
                model="m",
                prompt_tokens=120,
                completion_tokens=10,
                cache_hit_tokens=None,
                total_tokens=130,
                input_budget=None,
            ),
            purpose="default",
        )
        record_failed_usage(model="m", purpose="default", budget=None)
        report = current_usage()
        assert report["last_request"]["prompt_tokens"] is None
        assert report["last_request"]["failed"]
        assert report["cumulative"]["prompt_tokens"] == 120
        assert report["cumulative"]["prompt_tokens_unknown_calls"] == 1
