from __future__ import annotations


import pytest
from shiori_sdk.testing import FakeFrame, FakePluginContext

from shiori_sdk.lifecycle import AfterStepCtx
from plugins.context_pressure.backend.plugin import (
    setup,
    ContextPressureStopModule,
)


def _after_step_ctx(
    *, has_more: bool, tokens: int, limit: int | None = 100_000
) -> AfterStepCtx:
    return AfterStepCtx(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        iteration=1,
        context_tokens_estimate=tokens,
        tools_called=(),
        partial_reply="",
        tools_used_so_far=(),
        tool_chain_partial=(),
        partial_thinking=None,
        has_more=has_more,
        input_limit_tokens=limit,
    )


@pytest.mark.asyncio
async def test_requests_early_stop_at_the_budget_hard_limit() -> None:
    module = ContextPressureStopModule()
    ctx = _after_step_ctx(has_more=True, tokens=100_000)
    frame = FakeFrame(slots={"step:ctx": ctx})

    result = await module.run(frame)

    assert result.slots["step:early_stop_reason"] == "context_pressure"
    assert result.slots["step:telemetry:context_pressure_tokens"] == 100_000
    assert result.slots["step:telemetry:context_pressure_threshold"] == 100_000


@pytest.mark.asyncio
async def test_no_early_stop_below_the_budget_hard_limit() -> None:
    module = ContextPressureStopModule()
    ctx = _after_step_ctx(has_more=True, tokens=99_999)
    frame = FakeFrame(slots={"step:ctx": ctx})

    result = await module.run(frame)

    assert "step:early_stop_reason" not in result.slots


@pytest.mark.asyncio
async def test_no_early_stop_without_a_model_budget() -> None:
    module = ContextPressureStopModule()
    ctx = _after_step_ctx(has_more=True, tokens=10_000_000, limit=None)
    frame = FakeFrame(slots={"step:ctx": ctx})

    result = await module.run(frame)

    assert "step:early_stop_reason" not in result.slots


@pytest.mark.asyncio
async def test_no_early_stop_when_no_more_steps() -> None:
    module = ContextPressureStopModule()
    ctx = _after_step_ctx(has_more=False, tokens=100_001)
    frame = FakeFrame(slots={"step:ctx": ctx})

    result = await module.run(frame)

    assert "step:early_stop_reason" not in result.slots


async def test_setup_registers_modules(sdk_context: FakePluginContext) -> None:
    await setup(sdk_context)
    assert [
        type(module).__name__ for module in sdk_context.lifecycle.modules["after_step"]
    ] == ["ContextPressureStopModule"]
