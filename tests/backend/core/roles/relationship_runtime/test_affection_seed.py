from __future__ import annotations

import pytest

from core.roles.relationship_runtime.affection_seed import parse_affection_seed


def test_seed_accepts_an_integer_value_with_a_reason():
    seed = parse_affection_seed('```json\n{"value": 0, "reason": " 刚认识 "}\n```')
    assert (seed.value, seed.reason) == (0, "刚认识")


@pytest.mark.parametrize(
    "reply",
    [
        "好感大概 60",
        '{"value": "60", "reason": "字符串"}',
        '{"value": 60.5, "reason": "小数"}',
        '{"value": true, "reason": "布尔"}',
        '{"value": -1, "reason": "越界"}',
        '{"value": 60, "reason": "  "}',
        '{"value": 60}',
    ],
)
def test_seed_rejects_anything_but_a_valid_value_and_reason(reply):
    with pytest.raises(ValueError):
        parse_affection_seed(reply)
