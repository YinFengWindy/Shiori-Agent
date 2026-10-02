from agent.plugin_host.capabilities import BackgroundCapability
from agent.plugin_host.effects import EffectScope
import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent.plugin_host.kv import PluginKVStore
from shiori_sdk.testing.models import FakeChatProvider
from shiori_sdk.role_events import SceneObservationCommitted
from plugins.novelai.backend.auto_cg import AutoCgPolicy
from plugins.novelai.backend.auto_cg_controller import AutoCgController
from bootstrap.runtime.generations import RuntimeCandidate
from core.common.runtime_scope import bind_runtime, current_runtime_lease
from core.roles.store import RoleStore
from agent.plugin_host.roles import HostRoles


def _roles(workspace: Path, *, enabled: bool = True) -> HostRoles:
    roles = RoleStore(workspace)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.update(
        "novelai",
        lambda data: data.update({"mira": {"auto_scene_cg_enabled": enabled}}),
    )
    return HostRoles(roles)


def _observation(**overrides: Any) -> SceneObservationCommitted:
    payload = {
        "session_key": "role:mira",
        "channel": "desktop",
        "chat_id": "role:mira",
        "role_id": "mira",
        "source": "passive",
        "transition": "same",
        "scene_key": "rain",
        "visual_key": "rain-standing",
        "visual_description": "",
    }
    payload.update(overrides)
    return SceneObservationCommitted(**payload)


@pytest.mark.asyncio
async def test_cg_task_holds_generation_until_image_work_finishes(tmp_path):
    controller = AutoCgController(
        light_provider=FakeChatProvider(),
        light_model="light",
        prompt_provider=AsyncMock(
            return_value={
                "prompt": "1girl, rain",
                "negative_prompt": "blurry",
                "size_preset": "portrait",
            }
        ),
        role_store=_roles(tmp_path),
        policy=AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json")),
        session_manager=SimpleNamespace(
            get_or_create=lambda _: SimpleNamespace(metadata={})
        ),
        generate_tool=None,
        tool_registry=None,
        background=BackgroundCapability(EffectScope("test"), "test"),
    )
    started, finish = asyncio.Event(), asyncio.Event()
    observed = []

    async def run(*args, **kwargs):
        observed.append(current_runtime_lease().generation)
        started.set()
        await finish.wait()

    controller._run = run
    core = SimpleNamespace(
        stop=AsyncMock(side_effect=controller.terminate),
        memory_runtime=SimpleNamespace(aclose=AsyncMock()),
    )
    generation = RuntimeCandidate(3, core, SimpleNamespace())
    parent = generation.acquire()
    with bind_runtime(parent):
        controller.schedule(
            _observation(visual_description="少女站在雨里", transition="started")
        )
    await parent.release()
    await generation.retire()
    await started.wait()
    core.stop.assert_not_awaited()
    finish.set()
    await asyncio.wait_for(generation.drained.wait(), timeout=1)
    assert observed == [3]
    core.stop.assert_awaited_once()
