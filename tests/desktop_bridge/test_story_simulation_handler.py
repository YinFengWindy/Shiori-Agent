from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from story_simulation.errors import StoryInvalidOutputError
from story_simulation.catalog import StoryCatalog
from story_simulation.models import DirectorDraft, StoryBeatDraft, StoryPlayerProfile, StoryScene
from story_simulation.repository import StoryRepository, payload_hash

from desktop_bridge.story_simulation_handler import StorySimulationHandler


class OpeningDirector:
    """Small deterministic director for bridge-level Story tests."""

    async def generate(self, **_kwargs) -> DirectorDraft:
        return DirectorDraft(
            beats=(StoryBeatDraft(text="雨后的铃声响起。"),),
            visual_prompt="old school building, rainy afternoon",
            current_scene=StoryScene(key="old-school", character_ids=("role-1",)),
        )


class ProgressionVisualDirector:
    """Returns a visual prompt only after the player advances the Story."""

    def __init__(self) -> None:
        self.opening = True
        self.calls = 0

    async def generate(self, **_kwargs) -> DirectorDraft:
        self.calls += 1
        if self.opening:
            self.opening = False
            return DirectorDraft(
                beats=(StoryBeatDraft(text="雨后的铃声响起。"),),
                visual_prompt="old school building, rainy afternoon",
                current_scene=StoryScene(key="old-school", character_ids=("role-1",)),
            )
        return DirectorDraft(
            beats=(StoryBeatDraft(text="她把伞递到你手里。", kind="dialogue", speaker="澪"),),
            visual_prompt="rainy school gate, girl handing umbrella, emotional close-up",
            visual_type="character",
            current_scene=StoryScene(key="school-gate", character_ids=("role-1", "player")),
        )


class RepeatedCharacterVisualDirector:
    """Returns the same character visual again after it has already completed."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **_kwargs) -> DirectorDraft:
        self.calls += 1
        if self.calls == 1:
            return DirectorDraft(
                beats=(StoryBeatDraft(text="雨后的铃声响起。"),),
                visual_prompt="old school building, rainy afternoon",
                current_scene=StoryScene(key="old-school", character_ids=("role-1",)),
            )
        if self.calls <= 3:
            return DirectorDraft(
                beats=(StoryBeatDraft(text="她朝你伸出手。", kind="dialogue", speaker="澪"),),
                visual_prompt="rainy school gate, girl reaching hand, emotional close-up",
                visual_type="character",
                current_scene=StoryScene(key="school-gate", character_ids=("role-1", "player")),
            )
        return DirectorDraft(
            beats=(StoryBeatDraft(text="雨幕重新遮住了远处的校门。"),),
            visual_prompt="rainy school gate, empty scene, wet pavement, soft afternoon light",
            visual_type="scene",
            current_scene=StoryScene(key="school-gate", character_ids=("role-1", "player")),
        )


class RecordingImageTool:
    async def execute(self, **_kwargs):
        return json.dumps({"output_paths": ["D:\\stories\\opening.png"]})


class SequentialImageTool:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    async def execute(self, **kwargs):
        self.calls += 1
        self.prompts.append(str(kwargs["prompt"]))
        return json.dumps({"output_paths": [f"D:\\stories\\image-{self.calls}.png"]})


class RetryableImageTool:
    def __init__(self, *, fail_on_call: int = 1) -> None:
        self.calls = 0
        self.fail_on_call = fail_on_call

    async def execute(self, **_kwargs):
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("provider temporarily unavailable")
        path = "D:\\stories\\opening.png" if self.calls == 1 else "D:\\stories\\retry.png"
        return json.dumps({"output_paths": [path]})


class FailingOpeningDirector:
    async def generate(self, **_kwargs) -> DirectorDraft:
        raise StoryInvalidOutputError("invalid opening")


class FailTwiceOpeningDirector:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **_kwargs) -> DirectorDraft:
        self.calls += 1
        if self.calls <= 2:
            raise StoryInvalidOutputError("invalid opening")
        return DirectorDraft(
            beats=(StoryBeatDraft(text="雨后的铃声响起。"),),
            visual_prompt="old school building, rainy afternoon",
            current_scene=StoryScene(key="old-school", character_ids=("role-1",)),
        )


class BlockingOpeningDirector:
    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, **_kwargs) -> DirectorDraft:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return DirectorDraft(
            beats=(StoryBeatDraft(text="雨后的铃声响起。"),),
            visual_prompt="old school building, rainy afternoon",
            current_scene=StoryScene(key="old-school", character_ids=("role-1",)),
        )


class RecordingStoryProvider:
    def __init__(self, *, block_call: int | None = None) -> None:
        self.block_call = block_call
        self.calls: list[str] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def chat(self, **kwargs):
        self.calls.append(str(kwargs["model"]))
        if len(self.calls) == self.block_call:
            self.started.set()
            await self.release.wait()
        return SimpleNamespace(
            content=json.dumps(
                {
                    "beats": [{"text": "雨后的铃声响起。", "kind": "narration"}],
                    "current_scene": {
                        "key": "old-school",
                        "name": "旧校舍",
                        "character_ids": ["role-1"],
                    },
                    "visual_type": "scene",
                    "visual_prompt": "old school building, rainy afternoon",
                },
                ensure_ascii=False,
            )
        )


class RecordingStoryWorldRegistry:
    def __init__(self, *, model: str = "first-model", block_call: int | None = None) -> None:
        self.model = model
        self.provider = RecordingStoryProvider(block_call=block_call)
        self.activations: list[tuple[str, str, str]] = []

    async def get(self, role_id: str):
        self.role_id = role_id
        return self

    @contextmanager
    def activate_model(self, purpose: str):
        snapshot = SimpleNamespace(provider=self.provider, model=self.model)
        self.activations.append((self.role_id, purpose, self.model))
        yield snapshot


class MissingStoryWorldRegistry:
    async def get(self, _role_id: str):
        return self

    @contextmanager
    def activate_model(self, _purpose: str):
        raise ValueError("角色引用了不存在的模型注册: missing-model")
        yield


async def _wait_for_director_tasks(handler: StorySimulationHandler) -> None:
    for _ in range(30):
        if not handler._tasks:
            return
        await asyncio.sleep(0)
    raise AssertionError("Story Director task did not finish")


@pytest.mark.asyncio
async def test_create_story_generates_opening_and_replays_request(tmp_path) -> None:
    role = SimpleNamespace(
        id="role-1",
        to_dict=lambda: {"id": "role-1", "name": "澪", "system_prompt": "保持克制"},
    )
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda role_id: role if role_id == role.id else None),
        director=OpeningDirector(),
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }
    events: list[dict] = []

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=events.append)
    await asyncio.sleep(0)
    replay = await handler.handle("stories.create", payload, request_id="create-1", emit_event=events.append)
    story = (await handler.handle("stories.get", {"story_id": created["story"]["id"]}, request_id="get-1", emit_event=events.append))["story"]
    summaries = await handler.handle("stories.list", {}, request_id="list-1", emit_event=events.append)

    assert replay["turn_id"] == created["turn_id"]
    assert story["cues"][0]["text"] == "雨后的铃声响起。"
    assert story["turns"][0]["status"] == "committed"
    assert story["currentStoryDate"] == "2026-08-01"
    assert story["backgroundResource"]["status"] == "failed"
    assert summaries["stories"][0]["current_time_band"] == "上午"
    assert summaries["stories"][0]["current_story_date"] == "2026-08-01"
    assert summaries["stories"][0]["current_scene"] == {"key": "old-school", "name": "默认场景", "character_ids": ["role-1"]}
    await handler.aclose()


@pytest.mark.asyncio
async def test_story_turns_capture_the_role_dialogue_model_inside_each_task(tmp_path) -> None:
    role = SimpleNamespace(
        id="role-1",
        to_dict=lambda: {"id": "role-1", "name": "澪", "system_prompt": "保持克制"},
    )
    world_registry = RecordingStoryWorldRegistry(block_call=2)
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        world_registry=world_registry,
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    created = await handler.handle(
        "stories.create", payload, request_id="create-1", emit_event=lambda _event: None
    )
    await _wait_for_director_tasks(handler)
    story_id = created["story"]["id"]
    story = (
        await handler.handle(
            "stories.get",
            {"story_id": story_id},
            request_id="get-1",
            emit_event=lambda _event: None,
        )
    )["story"]

    await handler.handle(
        "stories.input",
        {
            "story_id": story_id,
            "input": "走进校舍。",
            "expected_revision": story["revision"],
        },
        request_id="input-1",
        emit_event=lambda _event: None,
    )
    await world_registry.provider.started.wait()
    world_registry.model = "second-model"
    world_registry.provider.release.set()
    await _wait_for_director_tasks(handler)
    story = (
        await handler.handle(
            "stories.get",
            {"story_id": story_id},
            request_id="get-2",
            emit_event=lambda _event: None,
        )
    )["story"]

    await handler.handle(
        "stories.continue",
        {"story_id": story_id, "expected_revision": story["revision"]},
        request_id="continue-1",
        emit_event=lambda _event: None,
    )
    await _wait_for_director_tasks(handler)

    assert world_registry.activations == [
        ("role-1", "chat", "first-model"),
        ("role-1", "chat", "first-model"),
        ("role-1", "chat", "second-model"),
    ]
    assert world_registry.provider.calls == ["first-model", "first-model", "second-model"]
    await handler.aclose()


@pytest.mark.asyncio
async def test_story_turn_fails_when_the_role_model_registration_is_missing(tmp_path) -> None:
    role = SimpleNamespace(
        id="role-1",
        to_dict=lambda: {"id": "role-1", "name": "澪", "system_prompt": "保持克制"},
    )
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        world_registry=MissingStoryWorldRegistry(),
    )
    events: list[dict] = []

    created = await handler.handle(
        "stories.create",
        {
            "title": "夏日来信",
            "background": "午后的旧校舍",
            "story_date": "2026-08-01",
            "time_band": "上午",
            "role_id": "role-1",
            "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
        },
        request_id="create-1",
        emit_event=events.append,
    )
    await _wait_for_director_tasks(handler)
    story = (
        await handler.handle(
            "stories.get",
            {"story_id": created["story"]["id"]},
            request_id="get-1",
            emit_event=events.append,
        )
    )["story"]

    assert story["turns"][0]["status"] == "failed"
    assert next(event for event in events if event["method"] == "stories.failed")["payload"]["code"] == "provider_not_configured"
    await handler.aclose()


@pytest.mark.asyncio
async def test_opening_background_is_saved_to_its_story_visual_gallery(tmp_path) -> None:
    role = SimpleNamespace(
        id="role-1",
        to_dict=lambda: {"id": "role-1", "name": "澪"},
    )
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=OpeningDirector(),
        image_tool=RecordingImageTool(),
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }
    events: list[dict] = []

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=events.append)
    for _ in range(4):
        await asyncio.sleep(0)
    story_id = created["story"]["id"]
    story = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-1", emit_event=events.append))["story"]
    gallery = await handler.handle("stories.cg.list", {}, request_id="gallery-1", emit_event=events.append)

    assert story["backgroundResource"]["status"] == "ready"
    assert story["backgroundResource"]["path"] == "D:\\stories\\opening.png"
    assert story["backgroundResource"]["sceneKey"] == "old-school"
    assert story["currentScene"] == {"key": "old-school", "name": "默认场景", "characterIds": ["role-1"]}
    assert gallery["stories"][0]["story_id"] == story_id
    assert gallery["stories"][0]["items"][0]["kind"] == "background"
    assert gallery["stories"][0]["items"][0]["id"] == story["backgroundResource"]["id"]
    assert any(event["method"] == "stories.resource.changed" for event in events)
    await handler.aclose()


@pytest.mark.asyncio
async def test_progression_visual_prompt_creates_async_cg_instead_of_opening_background(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=ProgressionVisualDirector(),
        image_tool=RecordingImageTool(),
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)
    for _ in range(8):
        await asyncio.sleep(0)
    story_id = created["story"]["id"]
    opening = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-1", emit_event=lambda _event: None))["story"]
    assert opening["backgroundResource"]["status"] == "ready"
    assert opening["cgGallery"][0]["kind"] == "background"

    await handler.handle(
        "stories.input",
        {"story_id": story_id, "input": "和她一起走。", "expected_revision": opening["revision"]},
        request_id="input-1",
        emit_event=lambda _event: None,
    )
    for _ in range(12):
        await asyncio.sleep(0)
    progressed = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-2", emit_event=lambda _event: None))["story"]

    assert progressed["backgroundResource"]["status"] == "ready"
    assert progressed["cgGallery"][1]["kind"] == "cg"
    assert progressed["cgGallery"][1]["visualType"] == "character"
    assert progressed["cgGallery"][1]["status"] == "ready"
    assert progressed["cgGallery"][1]["sceneKey"] == "school-gate"
    assert progressed["currentScene"] == {"key": "school-gate", "name": "默认场景", "characterIds": ["role-1", "player"]}
    assert progressed["cgGallery"][1]["sourceTurnId"] == progressed["turns"][-1]["id"]
    await handler.aclose()


@pytest.mark.asyncio
async def test_failed_progression_cg_can_retry_without_creating_a_new_turn(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    image_tool = RetryableImageTool(fail_on_call=2)
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=ProgressionVisualDirector(),
        image_tool=image_tool,
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    created = await handler.handle(
        "stories.create", payload, request_id="create-1", emit_event=lambda _event: None
    )
    story_id = created["story"]["id"]
    for _ in range(8):
        await asyncio.sleep(0)
    opening = (await handler.handle(
        "stories.get", {"story_id": story_id}, request_id="get-1", emit_event=lambda _event: None
    ))["story"]
    await handler.handle(
        "stories.input",
        {"story_id": story_id, "input": "和她一起走。", "expected_revision": opening["revision"]},
        request_id="input-1",
        emit_event=lambda _event: None,
    )
    for _ in range(12):
        await asyncio.sleep(0)
    failed = (await handler.handle(
        "stories.get", {"story_id": story_id}, request_id="get-2", emit_event=lambda _event: None
    ))["story"]
    resource_id = failed["cgGallery"][1]["id"]
    retry_events: list[dict] = []

    retrying = await handler.handle(
        "stories.cg.retry",
        {"story_id": story_id, "resource_id": resource_id},
        request_id="retry-1",
        emit_event=retry_events.append,
    )

    assert retrying["story"]["cgGallery"][1]["status"] == "generating"
    assert any(
        event["method"] == "stories.resource.changed"
        and event["payload"]["resource"]["status"] == "generating"
        for event in retry_events
    )
    persisted = await handler.handle(
        "stories.cg.list", {}, request_id="gallery-after-retry", emit_event=lambda _event: None
    )
    assert persisted["stories"][0]["items"][1]["status"] == "generating"
    assert len(retrying["story"]["turns"]) == 2
    for _ in range(8):
        await asyncio.sleep(0)
    ready = (await handler.handle(
        "stories.get", {"story_id": story_id}, request_id="get-2", emit_event=lambda _event: None
    ))["story"]

    assert ready["cgGallery"][1]["status"] == "ready"
    assert ready["cgGallery"][1]["path"] == "D:\\stories\\retry.png"
    assert len(ready["turns"]) == 2
    assert image_tool.calls == 3
    await handler.aclose()


@pytest.mark.asyncio
async def test_ready_cg_regeneration_replaces_the_existing_gallery_resource(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    image_tool = SequentialImageTool()
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=ProgressionVisualDirector(),
        image_tool=image_tool,
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)
    story_id = created["story"]["id"]
    for _ in range(8):
        await asyncio.sleep(0)
    opening = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-1", emit_event=lambda _event: None))["story"]
    await handler.handle(
        "stories.input",
        {"story_id": story_id, "input": "和她一起走。", "expected_revision": opening["revision"]},
        request_id="input-1",
        emit_event=lambda _event: None,
    )
    for _ in range(12):
        await asyncio.sleep(0)
    before = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-2", emit_event=lambda _event: None))["story"]
    original = before["cgGallery"][-1]

    regeneration_events: list[dict] = []
    regenerated = await handler.handle(
        "stories.cg.regenerate",
        {"story_id": story_id, "resource_id": original["id"]},
        request_id="regenerate-1",
        emit_event=regeneration_events.append,
    )
    replacement = regenerated["story"]["cgGallery"][-1]

    assert len(regenerated["story"]["cgGallery"]) == len(before["cgGallery"])
    assert regenerated["resource_id"] == original["id"]
    assert replacement["id"] == original["id"]
    assert replacement["kind"] == "cg"
    assert replacement["visualType"] == "character"
    assert replacement["prompt"] == original["prompt"]
    assert replacement["status"] == "generating"
    assert replacement["path"] == original["path"]
    assert any(
        event["method"] == "stories.resource.changed"
        and event["payload"]["resource"]["id"] == original["id"]
        and event["payload"]["resource"]["status"] == "generating"
        for event in regeneration_events
    )
    for _ in range(8):
        await asyncio.sleep(0)
    ready = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-3", emit_event=lambda _event: None))["story"]
    assert ready["cgGallery"][-1]["status"] == "ready"
    assert ready["cgGallery"][-1]["id"] == original["id"]
    assert ready["cgGallery"][-1]["path"] != original["path"]
    assert image_tool.calls == 3
    assert image_tool.prompts[-1] == original["prompt"]
    await handler.aclose()


@pytest.mark.asyncio
async def test_repeated_character_visual_does_not_create_another_cg_for_the_same_scene(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    image_tool = SequentialImageTool()
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=RepeatedCharacterVisualDirector(),
        image_tool=image_tool,
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)
    story_id = created["story"]["id"]
    for _ in range(8):
        await asyncio.sleep(0)
    opening = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-1", emit_event=lambda _event: None))["story"]
    await handler.handle(
        "stories.input",
        {"story_id": story_id, "input": "和她一起走。", "expected_revision": opening["revision"]},
        request_id="input-1",
        emit_event=lambda _event: None,
    )
    for _ in range(12):
        await asyncio.sleep(0)
    second = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-2", emit_event=lambda _event: None))["story"]
    assert len(second["cgGallery"]) == 2
    assert image_tool.calls == 2

    await handler.handle(
        "stories.input",
        {"story_id": story_id, "input": "她还在等你的回答。", "expected_revision": second["revision"]},
        request_id="input-2",
        emit_event=lambda _event: None,
    )
    for _ in range(12):
        await asyncio.sleep(0)
    repeated = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-3", emit_event=lambda _event: None))["story"]

    assert len(repeated["cgGallery"]) == 2
    assert repeated["cgGallery"][1]["visualType"] == "character"
    assert repeated["cgGallery"][1]["path"] == "D:\\stories\\image-2.png"
    assert image_tool.calls == 2

    await handler.handle(
        "stories.input",
        {"story_id": story_id, "input": "我们继续往前走。", "expected_revision": repeated["revision"]},
        request_id="input-3",
        emit_event=lambda _event: None,
    )
    for _ in range(12):
        await asyncio.sleep(0)
    scene = (await handler.handle("stories.get", {"story_id": story_id}, request_id="get-4", emit_event=lambda _event: None))["story"]

    assert len(scene["cgGallery"]) == 3
    assert scene["cgGallery"][2]["visualType"] == "scene"
    assert scene["cgGallery"][2]["path"] == "D:\\stories\\image-3.png"
    assert image_tool.calls == 3
    await handler.aclose()


@pytest.mark.asyncio
async def test_failed_opening_keeps_story_without_a_visual_resource(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=FailingOpeningDirector(),
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)
    for _ in range(8):
        await asyncio.sleep(0)
    story = (await handler.handle("stories.get", {"story_id": created["story"]["id"]}, request_id="get-1", emit_event=lambda _event: None))["story"]

    assert story["turns"][0]["status"] == "failed"
    assert story["backgroundResource"]["status"] == "failed"
    assert story["backgroundResource"]["errorCode"] == "director_invalid_output"
    await handler.aclose()


@pytest.mark.asyncio
async def test_failed_opening_retries_with_the_same_creation_request(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    director = FailTwiceOpeningDirector()
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=director,
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "creation_id": "creation-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    created = await handler.handle(
        "stories.create", payload, request_id="transport-1", emit_event=lambda _event: None
    )
    for _ in range(8):
        await asyncio.sleep(0)
    failed = (
        await handler.handle(
            "stories.get",
            {"story_id": created["story"]["id"]},
            request_id="get-1",
            emit_event=lambda _event: None,
        )
    )["story"]
    assert failed["turns"][0]["status"] == "failed"

    replay = await handler.handle(
        "stories.create", payload, request_id="transport-2", emit_event=lambda _event: None
    )
    for _ in range(12):
        await asyncio.sleep(0)
    retried = (
        await handler.handle(
            "stories.get",
            {"story_id": created["story"]["id"]},
            request_id="get-2",
            emit_event=lambda _event: None,
        )
    )["story"]

    assert replay["story"]["id"] == created["story"]["id"]
    assert retried["turns"][0]["status"] == "committed"
    assert retried["beats"]
    assert director.calls == 3
    await handler.aclose()


@pytest.mark.asyncio
async def test_story_recovery_restarts_an_interrupted_player_turn(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    catalog = StoryCatalog(tmp_path)
    catalog.create_entry(
        story_id="story-1",
        title="夏日来信",
        request_id="creation-1",
        payload_hash="creation-payload",
    )
    repository = StoryRepository(catalog.database_path("story-1"))
    repository.create_story(
        story_id="story-1",
        title="夏日来信",
        background="午后的旧校舍",
        role_snapshot=role.to_dict(),
        player_profile=StoryPlayerProfile("悠", "短发", "转学生"),
        story_date="2026-08-01",
        time_band="上午",
        opening_context={},
    )
    opening = repository.create_turn(
        story_id="story-1",
        input_text="",
        request_id="creation-1:opening",
        request_payload_hash=payload_hash(
            {"story_id": "story-1", "kind": "opening", "request_id": "creation-1:opening"}
        ),
        expected_revision=0,
        kind="opening",
    )
    opening_attempt = repository.start_attempt(opening["id"])
    repository.mark_validating(opening["id"], opening_attempt["attempt_id"])
    repository.commit_draft(
        turn_id=opening["id"],
        attempt_id=opening_attempt["attempt_id"],
        draft=DirectorDraft(
            beats=(StoryBeatDraft(text="开场。"),),
            current_scene=StoryScene(key="old-school", character_ids=("role-1",)),
        ),
        default_time_band="上午",
    )
    player = repository.create_turn(
        story_id="story-1",
        input_text="继续故事。",
        request_id="input-1",
        request_payload_hash=payload_hash({"story_id": "story-1", "input": "继续故事。"}),
        expected_revision=1,
    )
    original_attempt = repository.start_attempt(player["id"])
    repository.close()
    catalog.close()

    world_registry = RecordingStoryWorldRegistry(block_call=1)
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        world_registry=world_registry,
    )
    await handler.handle("stories.list", {}, request_id="list-1", emit_event=lambda _event: None)
    await world_registry.provider.started.wait()
    recovered = (
        await handler.handle(
            "stories.get",
            {"story_id": "story-1"},
            request_id="get-1",
            emit_event=lambda _event: None,
        )
    )["story"]

    assert recovered["turns"][1]["status"] == "generating"
    assert recovered["turns"][1]["attemptId"] != original_attempt["attempt_id"]
    assert world_registry.activations == [("role-1", "chat", "first-model")]
    world_registry.provider.release.set()
    await handler.aclose()


@pytest.mark.asyncio
async def test_create_story_rejects_exact_time_as_a_story_period(tmp_path) -> None:
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: None),
        director=OpeningDirector(),
    )

    with pytest.raises(ValueError, match="time_band"):
        await handler.handle(
            "stories.create",
            {
                "title": "夏日来信",
                "background": "午后的旧校舍",
                "story_date": "2026-08-01",
                "time_band": "2026-08-01T09:00:00+08:00",
                "role_id": "role-1",
                "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
            },
            request_id="create-1",
            emit_event=lambda _event: None,
        )
    await handler.aclose()


@pytest.mark.asyncio
async def test_create_story_recovers_from_an_interrupted_initialization(tmp_path) -> None:
    calls = {"to_dict": 0}

    def role_snapshot():
        calls["to_dict"] += 1
        if calls["to_dict"] == 1:
            raise RuntimeError("temporary role read failure")
        return {"id": "role-1", "name": "澪"}

    role = SimpleNamespace(id="role-1", to_dict=role_snapshot)
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=OpeningDirector(),
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    with pytest.raises(RuntimeError, match="temporary role read failure"):
        await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)

    assert created["story"]["id"].startswith("story-")
    await handler.aclose()


@pytest.mark.asyncio
async def test_create_story_reuses_a_provisioning_entry_after_process_restart(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "creation_id": "creation-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }
    catalog = StoryCatalog(tmp_path)
    catalog.create_entry(
        story_id="story-recovered",
        title=payload["title"],
        request_id=payload["creation_id"],
        payload_hash=payload_hash(payload),
    )
    catalog.close()

    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=OpeningDirector(),
    )
    created = await handler.handle(
        "stories.create", payload, request_id="transport-retry", emit_event=lambda _event: None
    )
    summaries = await handler.handle(
        "stories.list", {}, request_id="list-1", emit_event=lambda _event: None
    )

    assert created["story"]["id"] == "story-recovered"
    assert summaries["stories"][0]["story_id"] == "story-recovered"
    assert handler._catalog.require_entry("story-recovered")["status"] == "active"
    await handler.aclose()


@pytest.mark.asyncio
async def test_create_story_repairs_an_opening_turn_left_before_activation(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
        "story_date": "2026-08-01",
        "time_band": "上午",
        "role_id": "role-1",
        "creation_id": "creation-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }
    catalog = StoryCatalog(tmp_path)
    catalog.create_entry(
        story_id="story-partial",
        title=payload["title"],
        request_id=payload["creation_id"],
        payload_hash=payload_hash(payload),
    )
    repository = StoryRepository(catalog.database_path("story-partial"))
    repository.create_story(
        story_id="story-partial",
        title=payload["title"],
        background=payload["background"],
        role_snapshot=role.to_dict(),
        player_profile=StoryPlayerProfile(display_name="悠", appearance="短发", identity="转学生"),
        story_date="2026-08-01",
        time_band=payload["time_band"],
        opening_context={"background": payload["background"], "role_id": role.id},
    )
    repository.close()
    catalog.close()

    director = BlockingOpeningDirector()
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=director,
    )
    created = await handler.handle(
        "stories.create", payload, request_id="transport-retry", emit_event=lambda _event: None
    )
    replay = await handler.handle(
        "stories.create", payload, request_id="transport-retry-2", emit_event=lambda _event: None
    )
    await director.started.wait()

    assert replay["story"]["id"] == created["story"]["id"] == "story-partial"
    assert len(replay["story"]["turns"]) == 1
    assert director.calls == 1
    director.release.set()
    await handler.aclose()


@pytest.mark.asyncio
async def test_story_list_quarantines_an_active_entry_with_a_missing_database(tmp_path) -> None:
    catalog = StoryCatalog(tmp_path)
    catalog.create_entry(
        story_id="story-missing-db",
        title="残留剧情",
        request_id="creation-1",
        payload_hash="payload-hash",
    )
    catalog.set_status("story-missing-db", "active")
    catalog.close()

    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: None),
        director=OpeningDirector(),
    )
    summaries = await handler.handle(
        "stories.list", {}, request_id="list-1", emit_event=lambda _event: None
    )

    assert summaries == {"stories": []}
    assert handler._catalog.require_entry("story-missing-db")["status"] == "deleting"
    await handler.aclose()
