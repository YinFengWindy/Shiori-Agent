from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bus.event_bus import EventBus
from desktop_bridge.models import BridgeResponse
from desktop_bridge.server import DesktopBridgeServer
from session.manager import SessionManager


def _build_server(tmp_path: Path) -> DesktopBridgeServer:
    session_manager = SessionManager(tmp_path)
    runtime = SimpleNamespace(
        session_manager=SimpleNamespace(
            workspace=tmp_path,
            open_role_session=session_manager.open_role_session,
        ),
        loop=SimpleNamespace(process_direct=AsyncMock(return_value="ok")),
        event_bus=EventBus(),
    )
    return DesktopBridgeServer(runtime)


@pytest.mark.asyncio
async def test_health_response_is_not_blocked_by_slow_mutation(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    lines: asyncio.Queue[str | None] = asyncio.Queue()
    mutation_started = asyncio.Event()
    release_mutation = asyncio.Event()
    health_written = asyncio.Event()
    writes: list[dict[str, object]] = []

    async def _handle(request, emit_event):
        del emit_event
        method = str(request["method"])
        if method == "novelai.generate":
            mutation_started.set()
            await release_mutation.wait()
        return BridgeResponse(
            id=str(request["id"]),
            type="response",
            method=method,
            payload={"ok": True},
        )

    async def _write(payload: dict[str, object]) -> None:
        writes.append(payload)
        if payload["method"] == "health":
            health_written.set()

    server.service.handle = _handle
    await lines.put(json.dumps({"id": "slow", "method": "novelai.generate"}))
    await lines.put(json.dumps({"id": "health", "method": "health"}))
    serve_task = asyncio.create_task(
        server.serve_streams(read_line=lines.get, write_payload=_write)
    )

    await mutation_started.wait()
    await asyncio.wait_for(health_written.wait(), timeout=0.2)
    assert [payload["id"] for payload in writes] == ["health"]

    release_mutation.set()
    await lines.put(None)
    await serve_task
    assert {payload["id"] for payload in writes} == {"slow", "health"}


@pytest.mark.asyncio
async def test_server_uses_one_writer_for_concurrent_responses(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    lines = iter(
        [
            json.dumps({"id": str(index), "method": "health"})
            for index in range(4)
        ]
        + [None]
    )
    active_writes = 0
    peak_writes = 0
    writes: list[dict[str, object]] = []

    async def _read() -> str | None:
        return next(lines)

    async def _write(payload: dict[str, object]) -> None:
        nonlocal active_writes, peak_writes
        active_writes += 1
        peak_writes = max(peak_writes, active_writes)
        await asyncio.sleep(0)
        writes.append(payload)
        active_writes -= 1

    await server.serve_streams(read_line=_read, write_payload=_write)

    assert peak_writes == 1
    assert {payload["id"] for payload in writes} == {"0", "1", "2", "3"}


@pytest.mark.asyncio
async def test_server_eof_cancels_and_awaits_in_flight_request(tmp_path: Path) -> None:
    server = _build_server(tmp_path)
    lines = iter(
        [json.dumps({"id": "slow", "method": "novelai.generate"}), None]
    )
    cancelled = asyncio.Event()

    async def _read() -> str | None:
        return next(lines)

    async def _handle(request, emit_event):
        del request, emit_event
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def _write(_payload: dict[str, object]) -> None:
        raise AssertionError("cancelled request must not write a response")

    server.service.handle = _handle

    await asyncio.wait_for(
        server.serve_streams(read_line=_read, write_payload=_write),
        timeout=0.2,
    )
    assert cancelled.is_set()
