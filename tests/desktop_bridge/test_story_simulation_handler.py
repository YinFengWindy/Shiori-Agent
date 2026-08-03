from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from story_simulation.models import DirectorDraft, StoryBeatDraft

from desktop_bridge.story_simulation_handler import StorySimulationHandler


class OpeningDirector:
    """Small deterministic director for bridge-level Story tests."""

    async def generate(self, **_kwargs) -> DirectorDraft:
        return DirectorDraft(beats=(StoryBeatDraft(text="雨后的铃声响起。"),))


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
    assert summaries["stories"][0]["current_time_band"] == "上午"
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
