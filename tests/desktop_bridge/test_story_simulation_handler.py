from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from story_simulation.errors import StoryInvalidOutputError
from story_simulation.models import DirectorDraft, StoryBeatDraft

from desktop_bridge.story_simulation_handler import StorySimulationHandler


class OpeningDirector:
    """Small deterministic director for bridge-level Story tests."""

    async def generate(self, **_kwargs) -> DirectorDraft:
        return DirectorDraft(
            beats=(StoryBeatDraft(text="雨后的铃声响起。"),),
            visual_prompt="old school building, rainy afternoon",
        )


class RecordingImageTool:
    async def execute(self, **_kwargs):
        return json.dumps({"output_paths": ["D:\\stories\\opening.png"]})


class RetryableImageTool:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("provider temporarily unavailable")
        return json.dumps({"output_paths": ["D:\\stories\\retry.png"]})


class FailingOpeningDirector:
    async def generate(self, **_kwargs) -> DirectorDraft:
        raise StoryInvalidOutputError("invalid opening")


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
    assert story["backgroundResource"]["status"] == "failed"
    assert summaries["stories"][0]["current_time_band"] == "上午"
    await handler.aclose()


@pytest.mark.asyncio
async def test_opening_image_is_saved_to_its_story_cg_gallery(tmp_path) -> None:
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
    assert gallery["stories"][0]["story_id"] == story_id
    assert gallery["stories"][0]["items"][0]["id"] == story["backgroundResource"]["id"]
    assert any(event["method"] == "stories.resource.changed" for event in events)
    await handler.aclose()


@pytest.mark.asyncio
async def test_failed_opening_background_can_retry_without_creating_a_new_turn(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    image_tool = RetryableImageTool()
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=OpeningDirector(),
        image_tool=image_tool,
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
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
    failed = (await handler.handle(
        "stories.get", {"story_id": story_id}, request_id="get-1", emit_event=lambda _event: None
    ))["story"]
    resource_id = failed["backgroundResource"]["id"]

    retrying = await handler.handle(
        "stories.cg.retry",
        {"story_id": story_id, "resource_id": resource_id},
        request_id="retry-1",
        emit_event=lambda _event: None,
    )

    assert retrying["story"]["backgroundResource"]["status"] == "generating"
    assert len(retrying["story"]["turns"]) == 1
    for _ in range(8):
        await asyncio.sleep(0)
    ready = (await handler.handle(
        "stories.get", {"story_id": story_id}, request_id="get-2", emit_event=lambda _event: None
    ))["story"]

    assert ready["backgroundResource"]["status"] == "ready"
    assert ready["backgroundResource"]["path"] == "D:\\stories\\retry.png"
    assert len(ready["turns"]) == 1
    assert image_tool.calls == 2
    await handler.aclose()


@pytest.mark.asyncio
async def test_failed_opening_closes_background_resource_without_hiding_the_error(tmp_path) -> None:
    role = SimpleNamespace(id="role-1", to_dict=lambda: {"id": "role-1", "name": "澪"})
    handler = StorySimulationHandler(
        workspace=tmp_path,
        role_store=SimpleNamespace(get_role=lambda _role_id: role),
        director=FailingOpeningDirector(),
    )
    payload = {
        "title": "夏日来信",
        "background": "午后的旧校舍",
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
        "time_band": "上午",
        "role_id": "role-1",
        "player_profile": {"display_name": "悠", "appearance": "短发", "identity": "转学生"},
    }

    with pytest.raises(RuntimeError, match="temporary role read failure"):
        await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)

    created = await handler.handle("stories.create", payload, request_id="create-1", emit_event=lambda _event: None)

    assert created["story"]["id"].startswith("story-")
    await handler.aclose()
