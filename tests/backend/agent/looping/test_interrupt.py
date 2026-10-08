"""A detached turn's tasks skip interrupt tracking; turns started there do not (#721)."""

import asyncio

from agent.looping.interrupt import (
    TurnInterruptState,
    run_turn_task,
    tracked_turn_state,
)

STATES = {"role:mira": TurnInterruptState("role:mira", "hello")}


async def _state():
    return tracked_turn_state(STATES, "role:mira")


async def test_detached_turn_and_its_tasks_skip_tracking_but_new_turns_do_not():
    async def detached():
        # Work the turn spreads over tasks (observer fanout) is still the turn.
        part = await asyncio.create_task(_state())
        # A tracked turn started from inside it is tracked again.
        started = await asyncio.create_task(run_turn_task(_state, detached=False))
        return await _state(), part, started

    own, part, started = await asyncio.create_task(
        run_turn_task(detached, detached=True)
    )

    assert (own, part) == (None, None)
    assert started is STATES["role:mira"]
    assert await _state() is STATES["role:mira"]
