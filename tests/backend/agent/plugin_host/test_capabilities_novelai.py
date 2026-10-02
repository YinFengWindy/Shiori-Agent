"""Background capability keeps a runtime generation alive for NovelAI's auto CG.

The plugin is loaded through the real ``PluginKernel``; the CG task is reached
only through a published ``SceneObservationCommitted`` and the registered
``generate_image`` tool, so the host's ``spawn_runtime`` lease is exercised
without importing plugin internals. Controller scheduling rules live in
``plugins/novelai/tests/test_auto_cg_controller.py``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.role_events import SceneObservationCommitted
from shiori_sdk.testing.http import FakeHttp
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.provider import LLMResponse, ToolCall
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bootstrap.runtime.generations import RuntimeCandidate
from bus.event_bus import EventBus
from core.common.runtime_scope import bind_runtime, current_runtime_lease
from core.roles.store import RoleStore
from session.manager import SessionManager


def _prompt_provider() -> SimpleNamespace:
    """Light model that always submits one scene prompt."""
    return SimpleNamespace(
        chat=AsyncMock(
            return_value=LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        "cg",
                        "submit_scene_image_prompt",
                        {
                            "prompt": "1girl, rain",
                            "negative_prompt": "blurry",
                            "size_preset": "portrait",
                        },
                    )
                ],
            )
        )
    )


@pytest.mark.asyncio
async def test_cg_task_holds_generation_until_image_work_finishes(tmp_path: Path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.update(
        "novelai", lambda data: data.update({"mira": {"auto_scene_cg_enabled": True}})
    )
    sessions = SessionManager(tmp_path)
    sessions.open_role_session("mira", role_name="Mira")
    event_bus, registry = EventBus(), ToolRegistry()
    push_image = AsyncMock(return_value=None)
    push_tool = MessagePushTool(event_bus=event_bus)
    push_tool.register_channel("desktop", image=push_image)
    registry.register(push_tool)
    stage_plugin_package(plugin_directory("novelai"), tmp_path / "plugins/novelai")
    kernel = PluginKernel(
        [tmp_path / "plugins"],
        services=HostServices(
            http=FakeHttp(),
            light_provider=_prompt_provider(),
            light_model="light",
            event_bus=event_bus,
            tool_registry=registry,
            workspace=tmp_path,
            role_store=roles,
            session_manager=sessions,
            plugin_configs={"novelai": {"enabled": True, "token": "novel-token"}},
        ),
    )
    await kernel.load_all()
    generate_tool = registry.get_tool("generate_image")
    assert generate_tool is not None
    started, finish = asyncio.Event(), asyncio.Event()
    observed: list[int] = []
    image = str(tmp_path / "cg.png")

    async def generate(**_kwargs: object) -> str:
        observed.append(current_runtime_lease().generation)
        started.set()
        await finish.wait()
        return json.dumps({"output_paths": [image]})

    generate_tool.execute = generate
    core = SimpleNamespace(
        stop=AsyncMock(), memory_runtime=SimpleNamespace(aclose=AsyncMock())
    )
    generation = RuntimeCandidate(3, core, SimpleNamespace())
    parent = generation.acquire()
    with bind_runtime(parent):
        await event_bus.fanout(
            SceneObservationCommitted(
                session_key="role:mira",
                channel="desktop",
                chat_id="role:mira",
                role_id="mira",
                source="passive",
                transition="started",
                scene_key="rain",
                visual_key="rain-standing",
                visual_description="少女站在雨里",
            )
        )
    await parent.release()
    await generation.retire()
    await asyncio.wait_for(started.wait(), timeout=2)
    core.stop.assert_not_awaited()
    finish.set()
    await asyncio.wait_for(generation.drained.wait(), timeout=2)
    assert observed == [3]
    push_image.assert_awaited_once_with("role:mira", image)
    core.stop.assert_awaited_once()
    assert await kernel.unload("novelai") == []
