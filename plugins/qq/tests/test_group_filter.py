from __future__ import annotations

from plugins.qq.backend.channel.group_filter import (
    at_member_ids,
    reply_message_id,
    strip_at_segments,
)


def test_at_member_ids_lists_structural_mentions_only():
    raw = "[CQ:at,qq=10001] [CQ:at,qq=all] hi [CQ:at,qq=555,name=x] [CQ:at,qq=10001]"
    assert at_member_ids(raw) == ("10001", "555")
    assert at_member_ids("@10001 hi") == ()


def test_reply_message_id_reads_the_cq_reply_segment():
    assert reply_message_id("[CQ:reply,id=-2081231] [CQ:at,qq=1] hi") == "-2081231"
    assert reply_message_id("hi") is None


def test_strip_at_segments_removes_cq_at_codes():
    assert strip_at_segments("x [CQ:at,qq=10001] y") == "x  y".strip()
