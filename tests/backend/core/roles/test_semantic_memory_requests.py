from __future__ import annotations

import pytest

from core.roles.semantic_memory_requests import page_options


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
