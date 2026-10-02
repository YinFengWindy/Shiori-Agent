from __future__ import annotations

import pytest
from shiori_sdk.memory.requests import page_options, reject_undeclared_filters


def test_page_options_defaults_to_newest_first_and_bounds_paging() -> None:
    assert page_options({}) == (1, 20, "desc")
    assert page_options({"page": 0, "page_size": 500, "sort_order": "asc"}) == (
        1,
        100,
        "asc",
    )


@pytest.mark.parametrize("sort_by", ["updated_at", "created_at", "happened_at", ""])
def test_page_options_rejects_any_sort_field(sort_by: str) -> None:
    with pytest.raises(ValueError, match="sort_by is not supported"):
        page_options({"sort_by": sort_by})


def test_page_options_rejects_unknown_direction() -> None:
    with pytest.raises(ValueError, match="invalid sort order"):
        page_options({"sort_order": "latest"})


def test_reject_undeclared_filters_follows_the_engine_declaration() -> None:
    declared = {"memory_type": ["event"], "status": ["active"]}
    reject_undeclared_filters({"memory_type": "event", "status": "all"}, declared)
    reject_undeclared_filters({"q": "tea", "page": 2}, {})
    with pytest.raises(ValueError, match="unsupported memory filters: memory_domain$"):
        reject_undeclared_filters({"memory_domain": ""}, declared)
    with pytest.raises(
        ValueError, match="unsupported memory filters: memory_type, status"
    ):
        reject_undeclared_filters({"memory_type": "turn", "status": "all"}, {})
