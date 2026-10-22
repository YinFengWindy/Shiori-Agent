"""The kernel harness starts real plugins on stub services and awaits watchers."""

import asyncio
from dataclasses import dataclass

from shiori_sdk.kernel import Context, Key, PluginSpec
from shiori_sdk.testing.kernel import KernelHarness

CLOCK = Key[str]("clock")


@dataclass(frozen=True)
class Tick:
    at: str


async def test_idle_waits_for_watchers_fed_by_a_stub_service() -> None:
    seen: list[str] = []

    async def setup(ctx: Context) -> None:
        async def record(event: Tick) -> None:
            await asyncio.sleep(0.01)
            seen.append(f"{ctx.require(CLOCK)}:{event.at}")

        ctx.watch(Tick, record)

    harness = KernelHarness({CLOCK: "stub"})
    kernel = await harness.start(PluginSpec("ticker", setup, requires=("clock",)))
    _ = await kernel.emit(Tick("1"))
    assert seen == []

    await harness.idle()

    assert seen == ["stub:1"]
    assert await harness.stop() == []
