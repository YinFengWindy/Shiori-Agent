from __future__ import annotations

import sqlite3
from pathlib import Path
from dataclasses import replace

from PIL import Image
import pytest

from core.roles import RoleStore
from desktop_bridge.world_simulation_handler import WorldSimulationHandler
from world_simulation.errors import WorldNotFoundError
from world_simulation.service import WorldSimulationService


def _creation_input(role_id: str) -> dict[str, object]:
    return {
        "name": "雨港",
        "premise": "潮汐会带回被遗忘的名字。",
        "rules": "名字不能被轻易说出口。",
        "tone": "悬疑",
        "selectedRoleIds": [role_id],
        "seed": "rain-harbor-seed",
        "firstOc": {
            "name": "岚",
            "identity": "从北方来的抄写员",
            "entryTime": "2026-07-22T08:00:00+00:00",
            "entryLocation": "旧港",
            "primaryGoal": "找到失踪的姐姐",
        },
    }


def _create_world(
    handler: WorldSimulationHandler,
    role_id: str,
    *,
    name: str,
    request_prefix: str,
) -> dict[str, object]:
    input_data = _creation_input(role_id)
    input_data["name"] = name
    draft = handler.handle(
        "worlds.drafts.preview", input_data, request_id=f"{request_prefix}:preview"
    )
    assert draft is not None
    confirmed = handler.handle(
        "worlds.drafts.confirm",
        {
            "draft_id": draft["draft"]["id"],
            "native_identities": draft["draft"]["nativeIdentities"],
        },
        request_id=f"{request_prefix}:confirm",
    )
    assert confirmed is not None
    return confirmed["world"]


def test_each_world_uses_its_own_database_and_catalog_survives_restart(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(name="凛", system_prompt="保持冷静")
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    first = _create_world(handler, role.id, name="雨港", request_prefix="rain-harbor")
    second = _create_world(handler, role.id, name="雪原", request_prefix="snowfield")

    handler.handle(
        "worlds.actions.submit",
        {"world_id": first["id"], "content": "点亮旧港的灯。"},
        request_id="rain-harbor:action",
    )
    first_db = tmp_path / "worlds" / str(first["id"]) / "world.db"
    second_db = tmp_path / "worlds" / str(second["id"]) / "world.db"
    assert first_db.is_file()
    assert second_db.is_file()
    assert not (tmp_path / "worlds.db").exists()

    with sqlite3.connect(first_db) as connection:
        first_count = connection.execute(
            "SELECT COUNT(*) FROM timeline_events"
        ).fetchone()[0]
        first_world_ids = connection.execute("SELECT id FROM worlds").fetchall()
    with sqlite3.connect(second_db) as connection:
        second_count = connection.execute(
            "SELECT COUNT(*) FROM timeline_events"
        ).fetchone()[0]
        second_world_ids = connection.execute("SELECT id FROM worlds").fetchall()
    assert first_count == 2
    assert second_count == 1
    assert first_world_ids == [(first["id"],)]
    assert second_world_ids == [(second["id"],)]

    handler.close()
    restarted = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    listed = restarted.handle("worlds.list", {}, request_id="list-worlds")
    assert listed is not None
    assert {item["id"] for item in listed["worlds"]} == {
        first["id"],
        second["id"],
    }
    refreshed = restarted.handle(
        "worlds.get", {"world_id": second["id"]}, request_id="get-second"
    )
    assert refreshed is not None
    assert refreshed["world"]["name"] == "雪原"
    with pytest.raises(WorldNotFoundError):
        restarted.handle(
            "worlds.get", {"world_id": "world-does-not-exist"}, request_id="missing"
        )
    assert not (tmp_path / "worlds" / "world-does-not-exist").exists()
    restarted.close()


def test_copy_world_writes_a_prefix_into_a_new_database(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(name="凛", system_prompt="保持冷静")
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    source = _create_world(
        handler, role.id, name="原始世界", request_prefix="copy-source"
    )
    action = handler.handle(
        "worlds.actions.submit",
        {"world_id": source["id"], "content": "走进灯塔。"},
        request_id="copy-source:action",
    )
    assert action is not None
    source_events = handler._context(source["id"]).repository.list_events(source["id"])
    copied = handler.handle(
        "worlds.copy",
        {"world_id": source["id"], "anchor_id": source_events[-1].id},
        request_id="copy-world",
    )
    assert copied is not None
    copied_world = copied["world"]
    assert copied_world["id"] != source["id"]
    copied_db = tmp_path / "worlds" / str(copied_world["id"]) / "world.db"
    assert copied_db.is_file()
    with sqlite3.connect(copied_db) as connection:
        world_ids = connection.execute("SELECT id FROM worlds").fetchall()
        event_world_ids = connection.execute(
            "SELECT DISTINCT world_id FROM timeline_events"
        ).fetchall()
    assert world_ids == [(copied_world["id"],)]
    assert event_world_ids == [(copied_world["id"],)]
    handler.close()


def test_creation_draft_survives_handler_restart_and_freezes_role_snapshot(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        role_id="role-rin",
        name="凛",
        description="沉默的向导",
        system_prompt="保持冷静",
    )
    first_handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    draft = first_handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="preview-world",
    )
    assert draft is not None
    first_handler.close()

    role_store.update_role(role.id, description="已经改变的角色库资料")
    second_handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    world_result = second_handler.handle(
        "worlds.drafts.confirm",
        {
            "draft_id": draft["draft"]["id"],
            "native_identities": draft["draft"]["nativeIdentities"],
        },
        request_id="confirm-world",
    )

    assert world_result is not None
    world = world_result["world"]
    assert world["activeOcId"]
    assert world["ocs"][0]["name"] == "岚"
    assert world["relatedCharacters"][0]["relationship"] == "沉默的向导"
    second_handler.close()


def test_committed_world_is_recovered_after_catalog_registration_interruption(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(name="凛", system_prompt="保持冷静")
    first_handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    draft_response = first_handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="recovery-preview",
    )
    assert draft_response is not None
    draft = first_handler._catalog.get_draft(draft_response["draft"]["id"])
    assert draft is not None

    world_id = "world-recovered"
    first_handler._catalog.register_creation_intent(
        request_id="recovery-confirm",
        world_id=world_id,
        draft_id=draft.id,
        relative_db_path=first_handler._databases.relative_path(world_id),
    )
    repository = first_handler._databases.create(world_id)
    repository.save_draft(draft)
    WorldSimulationService(repository).confirm_world(
        draft.id,
        request_id="recovery-confirm",
        world_id=world_id,
        random_seed="recovery-seed",
    )
    first_handler.close()

    restarted = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    listed = restarted.handle("worlds.list", {}, request_id="recovery-list")

    assert listed is not None
    assert [item["id"] for item in listed["worlds"]] == [world_id]
    assert restarted._catalog.pending_creation_intents() == []
    recovered = restarted.handle(
        "worlds.get", {"world_id": world_id}, request_id="recovery-get"
    )
    assert recovered is not None
    assert recovered["world"]["name"] == "雨港"
    restarted.close()


def test_incomplete_creation_intent_removes_empty_world_database(tmp_path):
    role_store = RoleStore(tmp_path)
    catalog_handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    world_id = "world-incomplete"
    catalog_handler._catalog.register_creation_intent(
        request_id="incomplete-confirm",
        world_id=world_id,
        draft_id=None,
        relative_db_path=catalog_handler._databases.relative_path(world_id),
    )
    repository = catalog_handler._databases.create(world_id)
    repository.close()
    catalog_handler.close()

    restarted = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)

    assert restarted._catalog.pending_creation_intents() == []
    assert not (tmp_path / "worlds" / world_id).exists()
    restarted.close()


def test_copy_world_preserves_cross_database_scene_state_at_anchor(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(name="凛", system_prompt="保持冷静")
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    source = _create_world(handler, role.id, name="原始世界", request_prefix="state-source")
    context = handler._context(source["id"])
    world = context.repository.require_world(source["id"])
    run = context.service.start_run(
        source["id"],
        kind="scene",
        request_id="state-scene:run",
        expected_revision=world.revision,
        random_seed="state-scene",
    )
    proposal = handler._proposal(
        context=context,
        world=world,
        run_id=run.id,
        random_seed=run.random_seed,
        event_type="scene.choice.committed",
        effective_at=world.current_time,
        participants=(world.active_oc_id,),
        presentation={"mode": "scene", "kind": "dialogue", "content": "选择"},
    )
    proposal = replace(
        proposal,
        barrier={
            "id": "barrier-copy",
            "effective_at": world.current_time,
            "oc_id": world.active_oc_id,
            "reason": "需要选择方向",
        },
        scene_thread={
            "id": "scene-copy",
            "world_time": world.current_time,
            "location": "旧港",
            "participants": {world.active_oc_id: "岚"},
            "status": "active",
            "messages": ({"content": "选择"},),
        },
    )
    context.service.submit_action(proposal, request_id="state-scene")
    anchor = context.repository.list_events(source["id"])[-1]

    copied = handler.handle(
        "worlds.copy",
        {"world_id": source["id"], "anchor_id": anchor.id},
        request_id="state-copy",
    )

    assert copied is not None
    target_id = copied["world"]["id"]
    target = handler._context(target_id).repository
    barriers = target.list_pending_barriers(target_id)
    threads = target.list_scene_threads(target_id)
    session = target.get_presentation_session(target_id)
    assert [item.id for item in barriers] == ["barrier-copy"]
    assert [item.id for item in threads] == ["scene-copy"]
    assert threads[0].world_id == target_id
    assert session is not None
    assert session.status == "playing"
    handler.close()


def test_action_catch_up_only_returns_committed_beats(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(name="凛", system_prompt="保持冷静")
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    draft = handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="preview-world",
    )
    assert draft is not None
    confirmed = handler.handle(
        "worlds.drafts.confirm",
        {
            "draft_id": draft["draft"]["id"],
            "native_identities": draft["draft"]["nativeIdentities"],
        },
        request_id="confirm-world",
    )
    assert confirmed is not None
    world_id = str(confirmed["world"]["id"])

    accepted = handler.handle(
        "worlds.actions.submit",
        {"world_id": world_id, "content": "推开灯塔的门。"},
        request_id="submit-action",
    )
    replay = handler.handle(
        "worlds.events.catch_up",
        {"world_id": world_id, "cursor": "0"},
        request_id="catch-up",
    )
    repeated = handler.handle(
        "worlds.events.catch_up",
        {"world_id": world_id, "cursor": "0"},
        request_id="catch-up-repeat",
    )

    assert accepted is not None
    assert accepted["run_id"]
    assert replay is not None
    assert repeated is not None
    assert [beat["content"] for beat in replay["beats"]][-1] == "推开灯塔的门。"
    assert replay["world"]["scene"]["beats"][-1]["content"] == "推开灯塔的门。"
    assert replay["world"]["currentDayIndex"] == 1
    assert replay["world"]["days"][0]["status"] == "current"
    assert replay["world"]["days"][0]["events"][-1]["presentationMode"] == "narrative"
    assert "performancePlan" not in replay["beats"][-1]
    assert replay["presentation"]["plans"] == repeated["presentation"]["plans"] == []
    handler.close()


def test_presentation_session_checkpoints_pause_and_rebuilds_from_facts(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(name="凛", system_prompt="保持冷静")
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    draft = handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="preview-world",
    )
    assert draft is not None
    confirmed = handler.handle(
        "worlds.drafts.confirm",
        {
            "draft_id": draft["draft"]["id"],
            "native_identities": draft["draft"]["nativeIdentities"],
        },
        request_id="confirm-world",
    )
    assert confirmed is not None
    world = confirmed["world"]
    context = handler._context(world["id"])
    stored_world = context.repository.require_world(world["id"])
    run = context.service.start_run(
        world["id"],
        kind="scene",
        request_id="scene-presentation:run",
        expected_revision=stored_world.revision,
        random_seed="scene-presentation",
    )
    proposal = handler._proposal(
        context=context,
        world=stored_world,
        run_id=run.id,
        random_seed=run.random_seed,
        event_type="scene.encounter.committed",
        effective_at=stored_world.current_time,
        participants=(world["activeOcId"],),
        presentation={
            "mode": "scene",
            "kind": "dialogue",
            "content": "潮声里有人叫住了岚。",
        },
    )
    context.service.submit_action(proposal, request_id="scene-presentation")
    refreshed = handler.handle(
        "worlds.get", {"world_id": world["id"]}, request_id="refresh-scene"
    )
    assert refreshed is not None
    initial = refreshed["world"]["presentation"]
    assert initial["session"]["status"] == "playing"
    assert len(initial["plans"]) == 1
    assert refreshed["world"]["days"][0]["events"][-1]["presentationMode"] == "scene"
    plan_id = initial["plans"][0]["planId"]

    paused = handler.handle(
        "worlds.presentation.pause",
        {"world_id": world["id"]},
        request_id="pause-presentation",
    )
    assert paused is not None
    assert paused["presentation"]["session"]["status"] == "paused"
    resumed = handler.handle(
        "worlds.presentation.resume",
        {"world_id": world["id"]},
        request_id="resume-presentation",
    )
    assert resumed is not None
    assert resumed["presentation"]["session"]["status"] == "playing"

    checkpoint = handler.handle(
        "worlds.presentation.checkpoint",
        {"world_id": world["id"], "plan_id": plan_id, "cue_index": 0},
        request_id="checkpoint-presentation",
    )
    assert checkpoint is not None
    assert checkpoint["presentation"]["session"]["lastPresentedEventSequence"] == 2
    assert checkpoint["presentation"]["plans"] == []
    duplicate = handler.handle(
        "worlds.presentation.checkpoint",
        {"world_id": world["id"], "plan_id": plan_id, "cue_index": 0},
        request_id="duplicate-checkpoint",
    )
    assert duplicate == checkpoint

    context.repository.delete_presentation_session(world["id"])
    handler.close()
    restarted = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    rebuilt = restarted.handle(
        "worlds.get", {"world_id": world["id"]}, request_id="rebuild-session"
    )
    assert rebuilt is not None
    assert (
        rebuilt["world"]["presentation"]["session"]["lastPresentedEventSequence"] == 1
    )
    assert rebuilt["world"]["presentation"]["plans"]
    restarted.close()


def test_completing_a_day_commits_action_and_advances_one_day_atomically(tmp_path):
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(name="凛", system_prompt="保持冷静")
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    draft = handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="preview-day-world",
    )
    assert draft is not None
    confirmed = handler.handle(
        "worlds.drafts.confirm",
        {
            "draft_id": draft["draft"]["id"],
            "native_identities": draft["draft"]["nativeIdentities"],
        },
        request_id="confirm-day-world",
    )
    assert confirmed is not None
    world_id = confirmed["world"]["id"]

    first = handler.handle(
        "worlds.days.complete",
        {"world_id": world_id, "content": "去旧港寻找失踪者。"},
        request_id="complete-day-1",
    )
    repeated = handler.handle(
        "worlds.days.complete",
        {"world_id": world_id, "content": "去旧港寻找失踪者。"},
        request_id="complete-day-1",
    )
    result = handler.handle(
        "worlds.get", {"world_id": world_id}, request_id="get-day-2"
    )

    assert first == repeated
    assert result is not None
    world = result["world"]
    assert world["currentDayIndex"] == 2
    assert [day["status"] for day in world["days"]] == ["completed", "current"]
    assert [event["content"] for event in world["days"][0]["events"]][
        -1
    ] == "去旧港寻找失踪者。"
    assert world["days"][1]["events"][0]["content"] == "新的一天开始了。"
    assert len(handler._context(world_id).repository.list_events(world_id)) == 3
    handler.close()


def test_world_draft_freezes_role_visual_and_voice_snapshots(tmp_path):
    source = tmp_path / "portrait.png"
    source.write_bytes(b"world-owned-image")
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        name="凛",
        system_prompt="保持冷静",
        avatar_source=source,
        illustration_sources=[source],
    )
    role = role_store.update_role(
        role.id,
        runtime_config={
            "default_mood": "平静",
            "mood_catalog": ["平静"],
            "mood_illustration_bindings": {"平静": role.illustrations[0]},
            "tts": {
                "provider": "minimax",
                "voice_id": "rin-voice",
                "speed": 1.2,
                "secret_key": "must-not-be-copied",
            },
        },
    )
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    draft = handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="preview-world",
    )
    assert draft is not None
    stored = handler._catalog.get_draft(draft["draft"]["id"])
    assert stored is not None
    snapshot = stored.role_snapshots[0]
    copied_paths = [item["path"] for item in snapshot.assets]
    assert copied_paths and all(
        (tmp_path / "world_assets") in Path(path).parents for path in copied_paths
    )
    assert all(Path(path).is_file() for path in copied_paths)
    assert snapshot.voice_profile["voice_id"] == "rin-voice"
    assert "secret_key" not in snapshot.voice_profile
    role_store.delete_role(role.id)
    assert all(Path(path).is_file() for path in copied_paths)
    handler.close()


def test_world_snapshot_normalizes_character_canvas_and_foot_baseline(tmp_path):
    source = tmp_path / "legacy-character.png"
    image = Image.new("RGBA", (320, 480), (0, 0, 0, 0))
    image.paste((210, 90, 120, 255), (230, 80, 290, 440))
    image.save(source)
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        name="凛",
        system_prompt="保持冷静",
        avatar_source=source,
    )
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)

    draft = handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="preview-normalized-character",
    )

    assert draft is not None
    stored = handler._catalog.get_draft(draft["draft"]["id"])
    assert stored is not None
    normalized_path = Path(stored.role_snapshots[0].assets[0]["path"])
    with Image.open(normalized_path) as normalized:
        assert normalized.mode == "RGBA"
        assert normalized.size == (1200, 1600)
        bounds = normalized.getchannel("A").getbbox()
        assert bounds is not None
        assert abs((bounds[0] + bounds[2]) - 1200) <= 1
        assert bounds[3] == 1520
    handler.close()


def test_world_read_model_resolves_snapshot_visuals_for_sprite_cues(tmp_path):
    avatar_source = tmp_path / "avatar.png"
    mood_source = tmp_path / "mood.png"
    avatar_source.write_bytes(b"avatar")
    mood_source.write_bytes(b"mood")
    role_store = RoleStore(tmp_path)
    role = role_store.create_role(
        name="凛",
        system_prompt="保持冷静",
        avatar_source=avatar_source,
        illustration_sources=[mood_source],
    )
    role = role_store.update_role(
        role.id,
        runtime_config={
            "default_mood": "平静",
            "mood_catalog": ["平静"],
            "mood_illustration_bindings": {"平静": role.illustrations[0]},
        },
    )
    handler = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    draft = handler.handle(
        "worlds.drafts.preview",
        _creation_input(role.id),
        request_id="preview-visual-world",
    )
    assert draft is not None
    confirmed = handler.handle(
        "worlds.drafts.confirm",
        {
            "draft_id": draft["draft"]["id"],
            "native_identities": draft["draft"]["nativeIdentities"],
        },
        request_id="confirm-visual-world",
    )
    assert confirmed is not None
    world_id = confirmed["world"]["id"]
    context = handler._context(world_id)
    world = context.repository.require_world(world_id)
    resident = context.repository.list_residents(world_id)[0]
    run = context.service.start_run(
        world_id,
        kind="action",
        request_id="visual-action:run",
        expected_revision=world.revision,
        random_seed="visual-action",
    )
    proposal = handler._proposal(
        context=context,
        world=world,
        run_id=run.id,
        random_seed=run.random_seed,
        event_type="scene.action.committed",
        effective_at=world.current_time,
        participants=(resident.id,),
        presentation={
            "content": "她望向潮水。",
            "sprites": [{"actor_id": resident.id, "mood": "平静"}],
        },
    )
    context.service.submit_action(proposal, request_id="visual-action")

    result = handler.handle(
        "worlds.get", {"world_id": world_id}, request_id="get-visual-world"
    )

    assert result is not None
    sprite_cue = next(
        cue
        for plan in result["world"]["presentation"]["plans"]
        for cue in plan["cues"]
        if cue["kind"] == "sprites"
    )
    sprite = sprite_cue["payload"]["items"][0]
    assert Path(sprite["image_path"]).read_bytes() == b"mood"
    assert sprite["fallbackIds"] == [sprite["fallbackAssets"][0]["assetId"]]
    assert Path(sprite["fallbackAssets"][0]["image_path"]).read_bytes() == b"avatar"
    handler.close()
