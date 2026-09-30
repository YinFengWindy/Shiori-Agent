from __future__ import annotations

import pytest

from session.store.common import row_context_cursors


def test_row_context_cursors_rejects_a_partially_filled_row() -> None:
    """按上下文游标列只填了一列说明数据损坏，直接报错而不是回退到低水位。"""
    assert row_context_cursors({"user_cursor": None, "external_cursor": None}) is None
    assert row_context_cursors({"user_cursor": 3, "external_cursor": 5}) == {
        "user": 3,
        "external": 5,
    }
    with pytest.raises(ValueError, match="游标不完整"):
        row_context_cursors({"user_cursor": 3, "external_cursor": None})
