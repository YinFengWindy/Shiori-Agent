"""Admission and in-flight accounting of plugin call gates."""

from __future__ import annotations

import asyncio

import pytest
from shiori_sdk.rpc import PluginRpcError
from shiori_sdk.tools import Tool

from agent.plugin_host.call_gate import PluginCallGate


class _Blocking(Tool):
    name = "blocking"
    description = "waits for release"
    parameters = {"type": "object", "properties": {}}

    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def execute(self, **kwargs: object) -> str:
        await self.release.wait()
        return "done"


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_sealed_gate_rejects_waits_for_admitted_calls_and_can_reopen():
    gate = PluginCallGate("demo")
    release = asyncio.Event()

    async def call(value: int) -> int:
        await release.wait()
        return value

    guarded = gate.guard(call)
    running = asyncio.create_task(guarded(1))
    await _settle()
    gate.seal()
    with pytest.raises(PluginRpcError) as rejected:
        await guarded(2)
    assert rejected.value.code == "plugin_unavailable"
    idle = asyncio.create_task(gate.wait_idle())
    await _settle()
    assert not idle.done()

    release.set()
    assert await running == 1
    await asyncio.wait_for(idle, 1)
    gate.reopen()
    assert await guarded(3) == 3


@pytest.mark.asyncio
async def test_shared_tool_counts_each_call_for_every_gate_that_admitted_it():
    tool = _Blocking()
    old, new = PluginCallGate("demo"), PluginCallGate("demo")
    old.guard_tool(tool)
    # Another instance (e.g. the next generation) registers the same object.
    new.guard_tool(tool)
    first = asyncio.create_task(tool.execute())
    await _settle()
    old.seal()
    second = asyncio.create_task(tool.execute())
    await _settle()

    # The call admitted while both were open counts for both; once the old
    # gate is sealed only the new one admits.
    assert (old.in_flight, new.in_flight) == (1, 2)
    old_idle = asyncio.create_task(old.wait_idle())
    await _settle()
    assert not old_idle.done()
    tool.release.set()
    assert await first == await second == "done"
    await asyncio.wait_for(old_idle, 1)
    new.seal()
    with pytest.raises(PluginRpcError):
        await tool.execute()


@pytest.mark.asyncio
async def test_retired_gate_never_reopens_and_leaves_the_tool_gate_list():
    tool = _Blocking()
    tool.release.set()
    old, new = PluginCallGate("demo"), PluginCallGate("demo")
    old.guard_tool(tool)
    old.retire()
    old.reopen()
    with pytest.raises(PluginRpcError):
        await tool.execute()

    new.guard_tool(tool)
    assert tool.__dict__["__plugin_call_gates__"] == [new]
    assert await tool.execute() == "done"
