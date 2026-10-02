"""Policy thresholds, signatures and setup without any host runtime."""

import pytest
from pydantic import ValidationError
from plugins.tool_loop_guard.backend.plugin import setup
from shiori_sdk.tool_hooks import PreToolCtx
from shiori_sdk.testing.extensions import FakeExtensionContext


async def _context(config=None):
    ctx = FakeExtensionContext("tool_loop_guard", config=config)
    await setup(ctx)
    return ctx


def _event(
    name="dummy",
    arguments=None,
    *,
    session="cli:1",
    source="passive",
    batch=(),
    index=0,
):
    return PreToolCtx(
        session,
        "cli",
        "1",
        name,
        arguments or {"x": 1},
        source=source,
        tool_batch=batch,
        tool_batch_index=index,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config,limit",
    [
        (None, 3),
        ({"repeat_limit": 5}, 5),
        ({"repeat_limit": "5"}, 5),
        ({"repeat_limit": 2}, 2),
    ],
)
async def test_configured_threshold_applies_and_requests_finalize(config, limit):
    ctx = await _context(config)
    assert ctx.tool_hooks.handlers[0].handler_name == "detect_repeated_tool_call"
    for _ in range(limit - 1):
        assert (await ctx.tool_hooks.dispatch(_event())).decision == "pass"
    outcome = await ctx.tool_hooks.dispatch(_event())
    assert outcome.decision == "deny" and outcome.finalize
    assert f"{limit} 次" in outcome.reason
    await ctx.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["task_output", "task_stop"])
async def test_task_polling_is_excluded(name):
    ctx = await _context()
    for _ in range(8):
        assert (await ctx.tool_hooks.dispatch(_event(name))).decision == "pass"


@pytest.mark.asyncio
async def test_changed_arguments_order_session_and_source_do_not_share_repeat_counts():
    ctx = await _context()
    for n in range(5):
        assert (
            await ctx.tool_hooks.dispatch(_event(arguments={"x": n}))
        ).decision == "pass"
    for session, source in [("a", "passive"), ("b", "passive"), ("a", "subagent")]:
        for _ in range(2):
            assert (
                await ctx.tool_hooks.dispatch(_event(session=session, source=source))
            ).decision == "pass"


@pytest.mark.asyncio
async def test_batch_counts_once_and_ignores_polling_but_preserves_order():
    ctx = await _context()
    batch = (
        {"name": "task_output", "arguments": {}},
        {"name": "read", "arguments": {"x": 1}},
        {"name": "write", "arguments": {"x": 2}},
    )
    for turn in range(3):
        for index, call in enumerate(batch):
            outcome = await ctx.tool_hooks.dispatch(
                _event(call["name"], call["arguments"], batch=batch, index=index)
            )
            assert (outcome.decision == "deny") == (turn == 2 and index == 1)
    changed = (batch[0], batch[2], batch[1])
    assert (
        await ctx.tool_hooks.dispatch(_event("write", batch=changed, index=1))
    ).decision == "pass"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [1, "abc"])
async def test_invalid_config_is_not_coerced_to_a_default(value):
    ctx = FakeExtensionContext("tool_loop_guard", config={"repeat_limit": value})
    with pytest.raises(ValidationError, match="repeat_limit"):
        await setup(ctx)
    assert ctx.tool_hooks.handlers == []
