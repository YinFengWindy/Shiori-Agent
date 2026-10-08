"""Wakeup: a level-triggered signal with an optional clock deadline."""

import asyncio

from plugins.desktop_pet.backend.live_clock import Wakeup


async def test_wakeup_returns_on_set_or_deadline_and_remembers_an_early_set(clock):
    wakeup = Wakeup(clock)
    wakeup.set()
    await asyncio.wait_for(wakeup.wait(None), 1)

    waiting = asyncio.create_task(wakeup.wait(5))
    await clock.advance(4.9)
    assert not waiting.done()
    await clock.advance(0.1)
    assert waiting.done()

    waiting = asyncio.create_task(wakeup.wait(None))
    await clock.advance(100)
    assert not waiting.done()
    wakeup.set()
    await clock.settle()
    assert waiting.done()
