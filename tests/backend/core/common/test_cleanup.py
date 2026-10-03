import pytest
from unittest.mock import AsyncMock

from core.common.cleanup import run_cleanup_steps


@pytest.mark.asyncio
async def test_cleanup_continues_after_failure_and_reports_error():
    calls = []

    async def fail():
        calls.append("fail")
        raise RuntimeError("stop failed")

    async def cleanup():
        calls.append("cleanup")

    with pytest.raises(RuntimeError, match="stop failed"):
        await run_cleanup_steps(("fail", fail), ("cleanup", cleanup))
    assert calls == ["fail", "cleanup"]


@pytest.mark.asyncio
async def test_cleanup_keeps_reporting_only_the_first_error_by_default():
    first = ValueError("first failed")
    second = OSError("second failed")
    steps = [AsyncMock(side_effect=error) for error in (first, second)]
    finish = AsyncMock()
    with pytest.raises(ValueError) as caught:
        await run_cleanup_steps(
            ("first", steps[0]), ("second", steps[1]), ("finish", finish)
        )
    assert caught.value is first
    for step in (*steps, finish):
        step.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_can_aggregate_every_failure_and_still_run_final_release():
    first = ValueError("first failed")
    nested = ExceptionGroup("channel failures", [OSError("offline failed")])
    steps = [AsyncMock(side_effect=error) for error in (first, nested)]
    release = AsyncMock()
    with pytest.raises(ExceptionGroup) as caught:
        await run_cleanup_steps(
            ("first", steps[0]),
            ("second", steps[1]),
            ("release", release),
            aggregate_errors=True,
        )
    assert caught.value.exceptions == (first, nested)
    for step in (*steps, release):
        step.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_aggregation_succeeds_when_every_step_succeeds():
    step = AsyncMock()
    await run_cleanup_steps(("cleanup", step), aggregate_errors=True)
    step.assert_awaited_once()
