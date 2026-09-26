from __future__ import annotations

from plugins.qq.backend.channel.group_filter import is_at_bot, strip_at_segments


def test_is_at_bot_matches_only_the_account_mention():
    assert is_at_bot("[CQ:at,qq=10001] hi", "10001")
    assert not is_at_bot("[CQ:at,qq=555] hi", "10001")


def test_strip_at_segments_removes_cq_at_codes():
    assert strip_at_segments("x [CQ:at,qq=10001] y") == "x  y".strip()
