"""The independent fake makes result identity explicit and deduplicates reports."""

import pytest

from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.testing.background_results import (
    FakeBackgroundResults,
    FakeBackgroundResultTarget,
)


async def test_result_destination_must_be_configured_and_reports_once():
    fake = FakeBackgroundResults()
    capability: BackgroundResults = fake
    with pytest.raises(PermissionError):
        capability.capture()
    fake.target = FakeBackgroundResultTarget("role-a", "thread-a")
    target = capability.capture()
    assert (target.role_id, target.thread_id) == ("role-a", "thread-a")
    assert await target.report("run-a", "完整结果")
    assert not await target.report("run-a", "重复结果")
    assert fake.target.reports == {"run-a": "完整结果"}
