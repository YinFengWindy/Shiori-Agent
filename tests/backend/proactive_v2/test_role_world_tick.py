from __future__ import annotations

import pytest

from proactive_v2.loop import ProactiveLoop


@pytest.mark.asyncio
async def test_proactive_tick_uses_configured_role_dispatcher() -> None:
    loop = ProactiveLoop.__new__(ProactiveLoop)
    calls: list[str] = []

    async def tick() -> float:
        calls.append("tick")
        return 0.75

    async def dispatch(operation):
        calls.append("dispatch")
        return await operation()

    loop._tick = tick
    loop._tick_dispatcher = dispatch

    assert await loop._run_tick() == 0.75
    assert calls == ["dispatch", "tick"]
