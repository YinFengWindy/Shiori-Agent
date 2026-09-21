"""Host turn identity spans retries and cleanup is awaited on every exit path."""

import asyncio

import pytest

from agent.tools.turn_scope import ToolTurnScope, current_tool_turn, tool_turn


async def test_nested_retries_share_identity_and_child_reasoning_gets_own_turn():
    scopes = []
    released = []

    @tool_turn
    async def attempt():
        scope = current_tool_turn()
        scopes.append(scope)

        async def release():
            released.append(scope)

        scope.own("desktop", release)

    @tool_turn
    async def turn():
        await attempt()
        await attempt()
        assert not released
        await asyncio.create_task(attempt())
        assert released == [scopes[2]]

    await turn()
    assert scopes[0] is scopes[1] and scopes[0] is not scopes[2]
    assert released == [scopes[2], scopes[0]]


async def test_cancelled_turn_waits_for_release_and_blocks_late_children():
    entered, cleanup_started, cleanup_end = (asyncio.Event() for _ in range(3))
    scope = None

    @tool_turn
    async def turn():
        nonlocal scope
        scope = current_tool_turn()

        async def release():
            cleanup_started.set()
            await cleanup_end.wait()

        scope.own("driver", release)
        entered.set()
        await asyncio.Future()

    task = asyncio.create_task(turn())
    await entered.wait()
    task.cancel()
    await cleanup_started.wait()
    assert scope is not None and scope.closed
    assert not task.done()
    cleanup_end.set()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelled_finalizer_is_not_reported_as_success():
    scope = ToolTurnScope()

    async def release():
        raise asyncio.CancelledError("native cleanup cancelled")

    scope.own("driver", release)
    with pytest.raises(BaseExceptionGroup) as error:
        await scope.close()
    assert isinstance(error.value.exceptions[0], asyncio.CancelledError)
