from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bus.event_bus import EventBus
from core.roles import RoleRepository, RoleStore
from desktop_bridge.models import BridgeResponse
from desktop_bridge.server import DesktopBridgeServer, _build_observation_service
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager
from agent.tools.registry import ToolRegistry


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


def test_observation_service_prefers_dedicated_vl_provider(tmp_path: Path) -> None:
    role_store = SimpleNamespace()
    main_provider = SimpleNamespace(name="main")
    vl_provider = SimpleNamespace(name="vl")
    memory = SimpleNamespace()
    runtime = SimpleNamespace(
        config=SimpleNamespace(multimodal=False, model="main-model", vl_model="vl-model"),
        provider=main_provider,
        vl_provider=vl_provider,
        memory_runtime=SimpleNamespace(engine=memory),
    )

    service = _build_observation_service(runtime, role_store)

    assert service is not None
    assert service._model_adapter._provider is vl_provider
    assert service._model_adapter._model == "vl-model"


def test_observation_service_requires_a_visual_provider(tmp_path: Path) -> None:
    runtime = SimpleNamespace(
        config=SimpleNamespace(multimodal=False, model="text-model", vl_model=""),
        provider=SimpleNamespace(),
        vl_provider=None,
        memory_runtime=SimpleNamespace(engine=SimpleNamespace()),
    )

    assert _build_observation_service(runtime, SimpleNamespace()) is None


def test_observation_service_uses_main_provider_when_it_is_multimodal() -> None:
    main_provider = SimpleNamespace(name="main")
    runtime = SimpleNamespace(
        config=SimpleNamespace(multimodal=True, model="main-model", vl_model=""),
        provider=main_provider,
        vl_provider=None,
        memory_runtime=SimpleNamespace(engine=SimpleNamespace()),
    )

    service = _build_observation_service(runtime, SimpleNamespace())

    assert service is not None
    assert service._model_adapter._provider is main_provider
    assert service._model_adapter._model == "main-model"


def test_desktop_server_registers_screen_observation_as_a_role_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        DesktopBridgeService,
        "_build_novelai_service",
        lambda self: None,
    )
    runtime = SimpleNamespace(
        session_manager=SimpleNamespace(workspace=tmp_path),
        loop=SimpleNamespace(),
        event_bus=EventBus(),
        tools=ToolRegistry(),
        config=SimpleNamespace(multimodal=True, model="main-model", vl_model=""),
        provider=SimpleNamespace(),
        vl_provider=None,
        memory_runtime=SimpleNamespace(engine=SimpleNamespace()),
    )

    DesktopBridgeServer(runtime)

    assert runtime.tools.get_tool("observe_screen") is not None
    assert "observe_screen" in runtime.tools.get_always_on_names()


@pytest.mark.asyncio
async def test_observation_service_reads_roles_through_the_production_repository(
    tmp_path: Path,
) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        description="陪伴者",
        system_prompt="用中文回复",
    )
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content=(
                    '{"interface_summary":"空白画面","activity_key":"idle",'
                    '"targets":[],"risks":[],"bubble":"",'
                    '"experience_candidate":""}'
                ),
                tool_calls=[],
            )
        )
    )
    runtime = SimpleNamespace(
        config=SimpleNamespace(multimodal=True, model="main-model", vl_model=""),
        provider=provider,
        vl_provider=None,
        memory_runtime=SimpleNamespace(engine=SimpleNamespace()),
    )
    service = _build_observation_service(runtime, role_store)

    assert service is not None
    result = await service.analyze(
        {
            "role_id": "mira",
            "frame_id": "frame-1",
            "captured_at": "2026-07-23T12:00:00Z",
            "width": 64,
            "height": 64,
            "scale_factor": 1,
            "image_base64": base64.b64encode(b"\x89PNG\r\n\x1a\ncontent").decode(
                "ascii"
            ),
            "previous_observation": None,
            "recent_bubbles": [],
        }
    )

    assert result["activity_key"] == "idle"
    assert isinstance(service._model_adapter._roles, RoleRepository)
    assert service._model_adapter._roles is service._memory_writer._roles


@pytest.mark.asyncio
async def test_observation_service_validates_memory_roles_through_the_repository(
    tmp_path: Path,
) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="test")
    memory = SimpleNamespace(
        mutate=AsyncMock(
            return_value=SimpleNamespace(
                accepted=True,
                item_id="event-1",
                status="new",
                actual_kind="event",
            )
        )
    )
    runtime = SimpleNamespace(
        config=SimpleNamespace(multimodal=True, model="main-model", vl_model=""),
        provider=SimpleNamespace(),
        vl_provider=None,
        memory_runtime=SimpleNamespace(engine=memory),
    )
    service = _build_observation_service(runtime, role_store)

    assert service is not None
    result = await service.remember(
        {
            "role_id": "mira",
            "summary": "一起整理了报告",
            "happened_at": "2026-07-23T12:00:00Z",
            "source_ref": "desktop-observation:session-1:0",
        }
    )

    assert result["item_id"] == "event-1"


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
