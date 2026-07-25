from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from bus.events_lifecycle import DesktopPetActionRequested
from core.roles.store import RolePetPackage, RoleStore
from plugins.desktop_pet.tool import DesktopPetActionTool


def _build_tool(tmp_path: Path, *, clock_value: list[float]) -> tuple[DesktopPetActionTool, ToolRegistry]:
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(role_id="mira", name="Mira", system_prompt="test")
    store.replace_pet_packages(
        role.id,
        [
            RolePetPackage(
                id="pet-1",
                format="codex-sprite@1",
                display_name="Pet",
                manifest_path="assets/mira/pets/pet-1/pet.json",
                spritesheet_path="assets/mira/pets/pet-1/spritesheet.webp",
                imported_at="2026-07-25T00:00:00+08:00",
                actions={"greeting": "waving"},
            )
        ],
    )
    store.select_pet_package(role.id, "pet-1")
    store.update_role(role.id, desktop_pet_enabled=True)
    event_bus = EventBus()

    async def dispatch(event: DesktopPetActionRequested) -> DesktopPetActionRequested:
        event.dispatched = True
        return event

    event_bus.on(DesktopPetActionRequested, dispatch)
    registry = ToolRegistry()
    tool = DesktopPetActionTool(
        role_store=store,
        event_bus=event_bus,
        tool_registry=registry,
        clock=lambda: clock_value[0],
    )
    return tool, registry


async def _execute(
    tool: DesktopPetActionTool,
    registry: ToolRegistry,
    *,
    channel: str,
    timestamp: str = "2026-07-25T12:00:00+08:00",
    **arguments: str,
) -> dict[str, object]:
    registry.set_context(
        channel=channel,
        chat_id="role:mira",
        role_id="mira",
        session_key="role:mira",
        current_timestamp=timestamp,
    )
    return json.loads(await tool.execute(**arguments))


async def test_pet_action_rejects_external_channels(tmp_path: Path) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])

    result = await _execute(tool, registry, channel="telegram", action="move", target="center")

    assert result == {"accepted": False, "reason": "unsupported_channel"}


async def test_pet_action_dispatches_declared_play_action(tmp_path: Path) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])

    result = await _execute(tool, registry, channel="desktop", action="play", name="greeting")

    assert result["accepted"] is True
    assert result["action"] == "play"
    assert result["name"] == "greeting"


async def test_pet_action_rejects_unknown_action_and_enforces_limits(tmp_path: Path) -> None:
    clock = [0.0]
    tool, registry = _build_tool(tmp_path, clock_value=clock)

    unknown = await _execute(tool, registry, channel="desktop", action="play", name="sleep")
    first = await _execute(tool, registry, channel="desktop", action="move", target="center")
    clock[0] = 4.0
    same_turn = await _execute(tool, registry, channel="desktop", action="move", target="top_left")
    clock[0] = 4.1
    next_turn = await _execute(
        tool,
        registry,
        channel="desktop",
        timestamp="2026-07-25T12:01:00+08:00",
        action="move",
        target="top_left",
    )
    clock[0] = 5.0
    rate_limited = await _execute(
        tool,
        registry,
        channel="desktop",
        timestamp="2026-07-25T12:02:00+08:00",
        action="move",
        target="bottom_right",
    )

    assert unknown == {"accepted": False, "reason": "action_not_supported"}
    assert first["accepted"] is True
    assert same_turn == {"accepted": False, "reason": "turn_action_limit"}
    assert next_turn["accepted"] is True
    assert rate_limited == {"accepted": False, "reason": "rate_limited"}


async def test_pet_action_serializes_concurrent_calls_for_one_role(tmp_path: Path) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])
    started = asyncio.Event()
    release = asyncio.Event()

    async def dispatch(event: DesktopPetActionRequested) -> DesktopPetActionRequested:
        started.set()
        await release.wait()
        event.dispatched = True
        return event

    event_bus = EventBus()
    event_bus.on(DesktopPetActionRequested, dispatch)
    tool._event_bus = event_bus

    first = asyncio.create_task(
        _execute(tool, registry, channel="desktop", action="move", target="center")
    )
    await started.wait()
    second = asyncio.create_task(
        _execute(tool, registry, channel="desktop", action="move", target="top_left")
    )
    await asyncio.sleep(0)
    assert not second.done()

    release.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert first_result["accepted"] is True
    assert second_result == {"accepted": False, "reason": "rate_limited"}
