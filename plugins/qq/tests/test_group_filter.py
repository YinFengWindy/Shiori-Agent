from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from plugins.qq.backend.channel.group_filter import (
    DefaultGroupFilter,
    strip_at_segments,
)


@pytest.mark.asyncio
async def test_group_filter_accepts_allowed_user_with_required_at():
    group = SimpleNamespace(group_id="1", allow_from=["42"], require_at=True)
    event = SimpleNamespace(user_id="42", raw_message="[CQ:at,qq=10001] hi")

    accepted = await DefaultGroupFilter("10001").should_process(event, cast(Any, group))

    assert accepted is True


@pytest.mark.asyncio
async def test_group_filter_rejects_user_outside_allow_list():
    group = SimpleNamespace(group_id="1", allow_from=["42"], require_at=True)
    event = SimpleNamespace(user_id="9", raw_message="hi")

    accepted = await DefaultGroupFilter("10001").should_process(event, cast(Any, group))

    assert accepted is False


def test_strip_at_segments_removes_cq_at_codes():
    assert strip_at_segments("x [CQ:at,qq=10001] y") == "x  y".strip()
