from __future__ import annotations

from shiori_sdk.core.conversation import StepFinished
from shiori_sdk.testing import FakePluginContext

from plugins.context_pressure.backend.plugin import setup


def _step(*, has_more: bool, tokens: int, limit: int | None = 100_000) -> StepFinished:
    return StepFinished(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        iteration=1,
        context_tokens_estimate=tokens,
        input_limit_tokens=limit,
        tools_called=(),
        partial_reply="",
        partial_thinking=None,
        tools_used_so_far=(),
        tool_chain_partial=(),
        has_more=has_more,
    )


async def _finished(sdk_context: FakePluginContext, step: StepFinished) -> StepFinished:
    await setup(sdk_context)
    result = await sdk_context.emit(step)
    assert isinstance(result, StepFinished)
    return result


async def test_requests_early_stop_at_the_budget_hard_limit(
    sdk_context: FakePluginContext,
) -> None:
    result = await _finished(sdk_context, _step(has_more=True, tokens=100_000))

    assert (result.early_stop, result.early_stop_reason) == (True, "context_pressure")
    assert dict(result.extra_metadata) == {
        "context_pressure_tokens": 100_000,
        "context_pressure_threshold": 100_000,
    }


async def test_no_early_stop_below_the_budget_hard_limit(
    sdk_context: FakePluginContext,
) -> None:
    result = await _finished(sdk_context, _step(has_more=True, tokens=99_999))

    assert not result.early_stop


async def test_no_early_stop_without_a_model_budget(
    sdk_context: FakePluginContext,
) -> None:
    result = await _finished(
        sdk_context, _step(has_more=True, tokens=10_000_000, limit=None)
    )

    assert not result.early_stop


async def test_no_early_stop_when_no_more_steps(sdk_context: FakePluginContext) -> None:
    result = await _finished(sdk_context, _step(has_more=False, tokens=100_001))

    assert not result.early_stop
