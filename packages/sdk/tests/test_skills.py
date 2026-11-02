"""Explicit skill names are filtered without changing user mention order."""

from shiori_sdk.skills import collect_skill_mentions


def test_mentions_keep_first_appearance_order_and_ignore_unknown_names():
    assert collect_skill_mentions(
        "$unknown $second, $first $second", (name for name in ("first", "second"))
    ) == ["second", "first"]
