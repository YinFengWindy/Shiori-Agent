from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from shiori_sdk.testing.roles import FakeRoles
from shiori_sdk.testing.tools import FakeTools
from shiori_sdk.testing.memory_context import FakeRpc
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.desktop_pet.backend.tool import DesktopPetActionTool


def _build_tool(
    tmp_path: Path, *, clock_value: list[float]
) -> tuple[DesktopPetActionTool, FakeTools]:
    store = FakeRoles(tmp_path / "workspace")
    role = store.create_role(role_id="mira", name="Mira", system_prompt="test")
    RolePetStateStore(store).replace_packages(
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
    RolePetStateStore(store).select_package(role.id, "pet-1")
    RolePetStateStore(store).set_enabled(role.id, True)
    registry = FakeTools()
    tool = DesktopPetActionTool(
        role_store=store,
        rpc=FakeRpc(),
        tool_registry=registry,
        clock=lambda: clock_value[0],
    )
    return tool, registry


async def _execute(
    tool: DesktopPetActionTool,
    registry: FakeTools,
    *,
    channel: str,
    timestamp: str = "2026-07-25T12:00:00+08:00",
    **arguments: str,
) -> dict[str, object]:
    registry.context.update(
        channel=channel,
        chat_id="role:mira",
        role_id="mira",
        session_key="role:mira",
        current_timestamp=timestamp,
    )
    return json.loads(await tool.execute(**arguments))


def test_pet_action_schema_exposes_current_desktop_pet_state_and_actions(
    tmp_path: Path,
) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])
    registry.context.update(channel="desktop", role_id="mira", session_key="role:mira")
    registry.register(tool, always_on=True)

    function = tool.to_schema()["function"]
    description = function["description"]
    name_schema = function["parameters"]["properties"]["name"]

    assert "桌宠状态：已开启" in description
    assert "当前桌宠包：Pet" in description
    assert "可用动作：greeting" in description
    assert name_schema["enum"] == ["greeting"]


def test_pet_action_schema_reports_disabled_desktop_pet(tmp_path: Path) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])
    registry.context.update(channel="desktop", role_id="mira", session_key="role:mira")
    registry.register(tool, always_on=True)
    tool._state.set_enabled("mira", False)

    function = tool.to_schema()["function"]

    assert "桌宠状态：已关闭" in function["description"]
    assert function["parameters"]["properties"]["name"]["enum"] == []


@pytest.mark.asyncio
async def test_pet_action_rejects_external_channels(tmp_path: Path) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])

    result = await _execute(
        tool, registry, channel="telegram", action="move", target="center"
    )

    assert result == {"accepted": False, "reason": "unsupported_channel"}


@pytest.mark.asyncio
async def test_pet_action_dispatches_declared_play_action(tmp_path: Path) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])

    result = await _execute(
        tool, registry, channel="desktop", action="play", name="greeting"
    )

    assert result["accepted"] is True
    assert result["action"] == "play"
    assert result["name"] == "greeting"


@pytest.mark.asyncio
async def test_pet_action_rejects_unknown_action_and_enforces_limits(
    tmp_path: Path,
) -> None:
    clock = [0.0]
    tool, registry = _build_tool(tmp_path, clock_value=clock)

    unknown = await _execute(
        tool, registry, channel="desktop", action="play", name="sleep"
    )
    first = await _execute(
        tool, registry, channel="desktop", action="move", target="center"
    )
    clock[0] = 4.0
    same_turn = await _execute(
        tool, registry, channel="desktop", action="move", target="top_left"
    )
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


@pytest.mark.asyncio
async def test_pet_action_serializes_concurrent_calls_for_one_role(
    tmp_path: Path,
) -> None:
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])
    started = asyncio.Event()
    release = asyncio.Event()

    class Rpc(FakeRpc):
        async def emit(self, name, payload):
            started.set()
            await release.wait()
            return await super().emit(name, payload)

    tool._rpc = Rpc()

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


@pytest.mark.asyncio
async def test_no_connected_transport_does_not_consume_cooldown_or_turn(tmp_path: Path):
    tool, registry = _build_tool(tmp_path, clock_value=[0.0])

    class Rpc(FakeRpc):
        connected = False

        async def emit(self, name, payload):
            assert name == "action"
            assert payload["state"] == "waving"
            return self.connected

    rpc = Rpc()
    tool._rpc = rpc
    failed = await _execute(
        tool, registry, channel="desktop", action="play", name="greeting"
    )
    assert failed["accepted"] is False
    assert failed["reason"] == "desktop_bridge_unavailable"

    rpc.connected = True
    retried = await _execute(
        tool, registry, channel="desktop", action="play", name="greeting"
    )
    assert retried["accepted"] is True
