from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.qq.backend.channel.group_filter import (
    DefaultGroupFilter,
    QQGroupFilterConfig,
    strip_at_segments,
)


@pytest.mark.asyncio
async def test_group_filter_accepts_any_member_who_ats_the_bot():
    # Who may talk to the role is the binding's blacklist, not this filter (#398).
    group = QQGroupFilterConfig(group_id="1")
    event = SimpleNamespace(user_id="9", raw_message="[CQ:at,qq=10001] hi")

    assert await DefaultGroupFilter("10001").should_process(event, group) is True


@pytest.mark.asyncio
async def test_group_filter_ignores_message_that_does_not_at_the_bot():
    group = QQGroupFilterConfig(group_id="1")
    event = SimpleNamespace(user_id="9", raw_message="[CQ:at,qq=555] hi")

    assert await DefaultGroupFilter("10001").should_process(event, group) is False


@pytest.mark.asyncio
async def test_group_filter_without_require_at_accepts_plain_messages():
    group = QQGroupFilterConfig(group_id="1", require_at=False)
    event = SimpleNamespace(user_id="9", raw_message="hi")

    assert await DefaultGroupFilter("10001").should_process(event, group) is True


def test_strip_at_segments_removes_cq_at_codes():
    assert strip_at_segments("x [CQ:at,qq=10001] y") == "x  y".strip()
