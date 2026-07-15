from __future__ import annotations

import asyncio

import pytest

from desktop_bridge.stream_writer import BridgeStreamWriter


@pytest.mark.asyncio
async def test_stream_writer_serializes_concurrent_frames() -> None:
    active = 0
    peak = 0
    written: list[int] = []

    async def _write(payload: dict[str, object]) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        written.append(int(payload["sequence"]))
        active -= 1

    writer = BridgeStreamWriter(_write)
    await asyncio.gather(
        writer.write({"sequence": 1}),
        writer.write({"sequence": 2}),
        writer.write({"sequence": 3}),
    )
    await writer.aclose()

    assert peak == 1
    assert written == [1, 2, 3]


@pytest.mark.asyncio
async def test_stream_writer_propagates_underlying_failure() -> None:
    async def _write(_payload: dict[str, object]) -> None:
        raise OSError("pipe closed")

    writer = BridgeStreamWriter(_write)

    with pytest.raises(OSError, match="pipe closed"):
        await writer.write({"sequence": 1})
    with pytest.raises(OSError, match="pipe closed"):
        await writer.aclose()
