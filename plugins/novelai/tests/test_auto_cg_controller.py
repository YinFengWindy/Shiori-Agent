import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.plugin_host.kv import PluginKVStore
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bus.events_lifecycle import SceneObservationCommitted
from plugins.novelai.backend.auto_cg import AutoCgPolicy
from plugins.novelai.backend.auto_cg_controller import AutoCgController
from bootstrap.runtime.generations import RuntimeCandidate
from core.common.runtime_scope import bind_runtime, current_runtime_lease
from core.roles.store import RoleStore


def _roles(workspace: Path, *, enabled: bool = True) -> RoleStore:
    roles = RoleStore(workspace)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.update(
        "novelai",
        lambda data: data.update({"mira": {"auto_scene_cg_enabled": enabled}}),
    )
    return roles


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


def test_controller_advances_cooldown_for_passive_observations(tmp_path: Path) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    session_key = "role:mira"
    policy.advance_turn(session_key)
    policy.record_success(session_key, "rain")
    controller = AutoCgController(
        prompt_provider=AsyncMock(
            return_value={
                "prompt": "1girl, rain",
                "negative_prompt": "blurry",
                "size_preset": "portrait",
            }
        ),
        role_store=cast(Any, None),
        policy=policy,
        session_manager=cast(Any, None),
        generate_tool=cast(Any, None),
        tool_registry=cast(Any, None),
    )

    for _ in range(9):
        controller.schedule(_observation())

    assert policy.cooldown_remaining(session_key) == 0


@pytest.mark.asyncio
async def test_new_observation_cancels_stale_in_flight_task(tmp_path: Path) -> None:
    controller = AutoCgController(
        prompt_provider=AsyncMock(
            return_value={
                "prompt": "1girl, rain",
                "negative_prompt": "blurry",
                "size_preset": "portrait",
            }
        ),
        role_store=cast(Any, None),
        policy=AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json")),
        session_manager=cast(Any, None),
        generate_tool=cast(Any, None),
        tool_registry=cast(Any, None),
    )
    started = asyncio.Event()

    async def stale_work() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(stale_work())
    controller._tasks["role:mira"] = task
    await started.wait()
    controller.schedule(_observation(source="proactive"))
    await asyncio.sleep(0)

    assert task.cancelled()
    assert "role:mira" not in controller.tasks


@pytest.mark.asyncio
async def test_controller_records_state_only_after_image_push_succeeds(
    tmp_path: Path,
) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    push_tool = MessagePushTool()

    async def failing_image_sender(_chat_id: str, _image: str) -> None:
        raise RuntimeError("desktop unavailable")

    push_tool.register_channel("desktop", image=failing_image_sender)
    registry = ToolRegistry()
    registry.register(push_tool)

    class GenerateTool:
        async def execute(self, **_kwargs: Any) -> str:
            return '{"output_paths": ["cg.png"]}'

    controller = AutoCgController(
        prompt_provider=AsyncMock(
            return_value={
                "prompt": "1girl, rain",
                "negative_prompt": "blurry",
                "size_preset": "portrait",
            }
        ),
        role_store=cast(Any, None),
        policy=policy,
        session_manager=cast(Any, None),
        generate_tool=cast(Any, GenerateTool()),
        tool_registry=registry,
    )
    event = _observation(
        transition="started",
        visual_description="少女站在雨里",
    )

    with pytest.raises(RuntimeError, match="自动场景 CG 补发失败"):
        await controller._run(event, role_id="mira", bypass_cooldown=True)

    assert policy.cooldown_remaining("role:mira") == 0


@pytest.mark.asyncio
async def test_controller_retries_generation_once_and_pushes_one_image(
    tmp_path: Path,
) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    push_tool = MessagePushTool()
    pushed_images: list[str] = []

    async def image_sender(_chat_id: str, image: str) -> None:
        pushed_images.append(image)

    push_tool.register_channel("desktop", image=image_sender)
    registry = ToolRegistry()
    registry.register(push_tool)

    class GenerateTool:
        calls = 0

        async def execute(self, **_kwargs: Any) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary upstream failure")
            return '{"output_paths": ["first.png", "second.png"]}'

    generate_tool = GenerateTool()
    controller = AutoCgController(
        prompt_provider=AsyncMock(
            return_value={
                "prompt": "1girl, rain",
                "negative_prompt": "blurry",
                "size_preset": "portrait",
            }
        ),
        role_store=cast(Any, None),
        policy=policy,
        session_manager=cast(Any, SimpleNamespace()),
        generate_tool=cast(Any, generate_tool),
        tool_registry=registry,
    )

    await controller._run(
        _observation(
            transition="started",
            visual_description="少女站在雨里",
        ),
        role_id="mira",
        bypass_cooldown=True,
    )

    assert generate_tool.calls == 2
    assert pushed_images == ["first.png"]
    assert policy.cooldown_remaining("role:mira") > 0


@pytest.mark.asyncio
async def test_controller_abandons_after_one_generation_retry(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class GenerateTool:
        calls = 0

        async def execute(self, **_kwargs: Any) -> str:
            self.calls += 1
            raise RuntimeError("upstream unavailable")

    generate_tool = GenerateTool()
    controller = AutoCgController(
        prompt_provider=AsyncMock(
            return_value={
                "prompt": "1girl, rain",
                "negative_prompt": "blurry",
                "size_preset": "portrait",
            }
        ),
        role_store=cast(Any, None),
        policy=AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json")),
        session_manager=cast(Any, None),
        generate_tool=cast(Any, generate_tool),
        tool_registry=cast(Any, None),
    )

    with caplog.at_level("ERROR"):
        media = await controller._generate_media_with_retry(
            {"prompt": "rain"},
            session_key="role:mira",
        )

    assert media == []
    assert generate_tool.calls == 2
    assert "已重试 1 次" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["disabled", "duplicate", "cooldown", "manual"])
async def test_prompt_model_is_not_called_for_ineligible_cg(tmp_path, blocked):
    policy = AutoCgPolicy(PluginKVStore(tmp_path / "kv.json"))
    if blocked in {"duplicate", "cooldown"}:
        policy.record_success(
            "role:mira", "rain-standing" if blocked == "duplicate" else "old"
        )
    prompt = AsyncMock()
    controller = AutoCgController(
        role_store=_roles(tmp_path, enabled=blocked != "disabled"),
        policy=policy,
        session_manager=SimpleNamespace(
            get_or_create=lambda _: SimpleNamespace(metadata={})
        ),
        generate_tool=None,
        tool_registry=None,
        prompt_provider=prompt,
    )
    controller.schedule(
        _observation(
            transition="same" if blocked == "cooldown" else "started",
            visual_description="少女站在雨里",
            tools_used=("generate_image",) if blocked == "manual" else (),
        )
    )
    await asyncio.gather(*controller.tasks.values())
    prompt.assert_not_awaited()
    await controller.terminate()
