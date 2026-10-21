from shiori_sdk.testing.models import FakeChatProvider
from shiori_sdk.testing.extensions import FakeBackground
from shiori_sdk.testing.context import FakePluginContext
import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.testing.storage import FakeKV

from shiori_sdk.role_events import SceneObservationCommitted
from plugins.novelai.backend.auto_cg import AutoCgPolicy
from plugins.novelai.backend.auto_cg_controller import AutoCgController
from plugins.novelai.backend.role_state import NovelAIRoleState
from shiori_sdk.testing.roles import FakeRoles


def _roles(workspace: Path, *, enabled: bool = True) -> FakeRoles:
    roles = FakeRoles(workspace)
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


def test_controller_advances_cooldown_for_passive_observations(tmp_path: Path) -> None:
    policy = AutoCgPolicy(FakeKV())
    session_key = "role:mira"
    policy.advance_turn(session_key)
    policy.record_success(session_key, "rain")
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
        role_store=cast(Any, None),
        policy=policy,
        session_manager=cast(Any, None),
        generate_tool=cast(Any, None),
        tool_registry=cast(Any, None),
        background=FakeBackground(FakePluginContext()),
    )

    for _ in range(9):
        controller.schedule(_observation())

    assert policy.cooldown_remaining(session_key) == 0


@pytest.mark.asyncio
async def test_new_observation_cancels_stale_in_flight_task(tmp_path: Path) -> None:
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
        role_store=cast(Any, None),
        policy=AutoCgPolicy(FakeKV()),
        session_manager=cast(Any, None),
        generate_tool=cast(Any, None),
        tool_registry=cast(Any, None),
        background=FakeBackground(FakePluginContext()),
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
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_generated_cg_keeps_cooldown_and_dedup_after_delivery_fails(
    tmp_path: Path,
    failure,
) -> None:
    policy = AutoCgPolicy(FakeKV())
    push_tool = SimpleNamespace(
        name="message_push", execute=AsyncMock(return_value="图片已发送")
    )
    registry = SimpleNamespace(
        get_tool=lambda name: push_tool if name == "message_push" else None
    )

    class GenerateTool:
        calls = 0

        async def execute(self, **_kwargs: Any) -> str:
            self.calls += 1
            return '{"output_paths": ["cg.png"]}'

    generate_tool = GenerateTool()
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
        policy=policy,
        session_manager=SimpleNamespace(
            get_or_create=lambda _: SimpleNamespace(metadata={})
        ),
        generate_tool=cast(Any, generate_tool),
        tool_registry=registry,
        background=FakeBackground(FakePluginContext()),
    )
    event = _observation(
        transition="started",
        visual_description="少女站在雨里",
    )

    push_tool.execute.side_effect = failure("desktop unavailable")
    with pytest.raises(failure, match="desktop unavailable"):
        await controller._run(event, role_id="mira", bypass_cooldown=True)

    assert policy.cooldown_remaining("role:mira") > 0

    # A new visual in the same scene stays in cooldown, even after failed delivery.
    controller.schedule(
        _observation(visual_key="rain-seated", visual_description="少女坐在雨里")
    )
    await asyncio.gather(*controller.tasks.values())
    # Scene starts bypass cooldown, but must not regenerate this successful image.
    await controller._run(event, role_id="mira", bypass_cooldown=True)
    assert generate_tool.calls == 1
    push_tool.execute.assert_awaited_once()
    await controller.terminate()


@pytest.mark.asyncio
async def test_external_cg_uses_original_chat_account_supplement() -> None:
    account_tool = SimpleNamespace(execute=AsyncMock(return_value="accepted"))
    desktop_tool = SimpleNamespace(execute=AsyncMock())
    tools = {"account_send": account_tool, "message_push": desktop_tool}
    controller = AutoCgController(
        light_provider=FakeChatProvider(),
        light_model="light",
        prompt_provider=AsyncMock(return_value={"prompt": "1girl, rain"}),
        role_store=cast(Any, None),
        policy=AutoCgPolicy(FakeKV()),
        session_manager=cast(Any, None),
        generate_tool=cast(
            Any,
            SimpleNamespace(
                execute=AsyncMock(return_value='{"output_paths":["cg.png"]}')
            ),
        ),
        tool_registry=SimpleNamespace(get_tool=tools.get),
        background=FakeBackground(FakePluginContext()),
    )
    await controller._run(
        _observation(
            channel="qqbot", chat_id="c2c:bot:peer", visual_description="少女站在雨里"
        ),
        role_id="mira",
        bypass_cooldown=True,
    )
    account_tool.execute.assert_awaited_once_with(
        channel="qqbot",
        target_kind="user",
        role_id="mira",
        session_key="role:mira",
        push_chat_id="c2c:bot:peer",
        push_proactive=False,
        media=["cg.png"],
    )
    desktop_tool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_controller_retries_generation_once_and_pushes_one_image(
    tmp_path: Path,
) -> None:
    policy = AutoCgPolicy(FakeKV())
    pushed_images: list[str] = []

    async def image_sender(_chat_id: str, image: str) -> None:
        pushed_images.append(image)

    push_tool = SimpleNamespace(
        name="message_push", execute=AsyncMock(return_value="图片已发送")
    )
    registry = SimpleNamespace(
        get_tool=lambda name: push_tool if name == "message_push" else None
    )

    class GenerateTool:
        calls = 0

        async def execute(self, **_kwargs: Any) -> str:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary upstream failure")
            return '{"output_paths": ["first.png", "second.png"]}'

    generate_tool = GenerateTool()
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
        role_store=cast(Any, None),
        policy=policy,
        session_manager=cast(Any, SimpleNamespace()),
        generate_tool=cast(Any, generate_tool),
        tool_registry=registry,
        background=FakeBackground(FakePluginContext()),
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
    assert push_tool.execute.await_args.kwargs["image"] == "first.png"
    assert push_tool.execute.await_args.kwargs["push_proactive"] is False
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
    policy = AutoCgPolicy(FakeKV())
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
        role_store=cast(Any, None),
        policy=policy,
        session_manager=cast(Any, None),
        generate_tool=cast(Any, generate_tool),
        tool_registry=cast(Any, None),
        background=FakeBackground(FakePluginContext()),
    )

    with caplog.at_level("ERROR"):
        await controller._run(
            _observation(visual_description="少女站在雨里"),
            role_id="mira",
            bypass_cooldown=True,
        )

    assert generate_tool.calls == 2
    assert policy.cooldown_remaining("role:mira") == 0
    assert "已重试 1 次" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["disabled", "duplicate", "cooldown", "manual"])
async def test_prompt_model_is_not_called_for_ineligible_cg(tmp_path, blocked):
    policy = AutoCgPolicy(FakeKV())
    if blocked in {"duplicate", "cooldown"}:
        policy.record_success(
            "role:mira", "rain-standing" if blocked == "duplicate" else "old"
        )
    prompt = AsyncMock()
    controller = AutoCgController(
        light_provider=FakeChatProvider(),
        light_model="light",
        role_store=_roles(tmp_path, enabled=blocked != "disabled"),
        policy=policy,
        session_manager=SimpleNamespace(
            get_or_create=lambda _: SimpleNamespace(metadata={})
        ),
        generate_tool=None,
        tool_registry=None,
        prompt_provider=prompt,
        background=FakeBackground(FakePluginContext()),
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


@pytest.mark.asyncio
async def test_cg_work_is_spawned_as_runtime_retaining_background(tmp_path: Path):
    """CG generation must ask the host to retain the runtime until it finishes."""

    class RecordingBackground(FakeBackground):
        def __init__(self) -> None:
            super().__init__(FakePluginContext())
            self.runtime_names: list[str] = []

        def spawn(self, coro, *, name):
            raise AssertionError("auto CG must not use a non-retaining task")

        def spawn_runtime(self, coro, *, name):
            self.runtime_names.append(name)
            return asyncio.create_task(coro, name=name)

    background = RecordingBackground()
    controller = AutoCgController(
        light_provider=FakeChatProvider(),
        light_model="light",
        prompt_provider=AsyncMock(return_value=None),
        role_store=_roles(tmp_path),
        policy=AutoCgPolicy(FakeKV()),
        session_manager=SimpleNamespace(
            get_or_create=lambda _: SimpleNamespace(metadata={})
        ),
        generate_tool=None,
        tool_registry=None,
        background=background,
    )

    controller.schedule(
        _observation(visual_description="少女站在雨里", transition="started")
    )
    await controller.terminate()

    assert background.runtime_names == ["novelai_auto_cg:role:mira"]


@pytest.mark.asyncio
async def test_schedule_freezes_each_roles_instructions_and_reuses_generated_prompt(
    tmp_path,
):
    roles = _roles(tmp_path)
    roles.create_role(role_id="rina", name="Rina", system_prompt="test")
    roles.extensions.update(
        "novelai",
        lambda data: NovelAIRoleState.write_draft(
            "rina", {"autoSceneCgEnabled": True}, data
        ),
    )
    state = NovelAIRoleState(roles)
    state.save_prompt_instructions("mira", "保留猫耳")
    state.save_prompt_instructions("rina", "全身构图")
    prompt = AsyncMock(
        return_value={
            "prompt": "1girl, cat ears",
            "negative_prompt": "",
            "size_preset": "portrait",
        }
    )
    generate = AsyncMock(
        side_effect=[RuntimeError("retry"), *['{"output_paths": ["cg.png"]}'] * 3]
    )
    push = SimpleNamespace(execute=AsyncMock(return_value="已发送"))
    controller = AutoCgController(
        light_provider=FakeChatProvider(),
        light_model="light",
        role_store=roles,
        policy=AutoCgPolicy(FakeKV()),
        session_manager=SimpleNamespace(
            get_or_create=lambda _: SimpleNamespace(metadata={})
        ),
        generate_tool=SimpleNamespace(execute=generate),
        tool_registry=SimpleNamespace(get_tool=lambda _: push),
        prompt_provider=prompt,
        background=FakeBackground(FakePluginContext()),
    )
    for role_id in ("mira", "rina"):
        controller.schedule(
            _observation(
                role_id=role_id,
                session_key=f"role:{role_id}",
                transition="started",
                visual_description="少女站在雨里",
            )
        )
    # Change after scheduling but before the background coroutines start.
    state.save_prompt_instructions("mira", "新的要求")
    await asyncio.gather(*controller.tasks.values())
    assert {
        call.kwargs["event"].role_id: call.kwargs["prompt_instructions"]
        for call in prompt.await_args_list
    } == {"mira": "保留猫耳", "rina": "全身构图"}
    assert prompt.await_count == 2
    assert generate.await_count == 3
    generated_prompts = [call.kwargs["prompt"] for call in generate.await_args_list]
    assert len(set(generated_prompts)) == 1, "retries reuse the same prepared prompt"
    assert "1girl, cat ears" in generated_prompts[0]
    assert all(text not in generated_prompts[0] for text in ("保留猫耳", "全身构图"))

    controller.schedule(
        _observation(
            transition="changed", visual_key="new-view", visual_description="少女坐下"
        )
    )
    await asyncio.gather(*controller.tasks.values())
    assert prompt.await_args.kwargs["prompt_instructions"] == "新的要求"
    await controller.terminate()
