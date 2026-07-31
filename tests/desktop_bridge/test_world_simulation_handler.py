from __future__ import annotations

from pathlib import Path

from PIL import Image

from core.roles import RoleStore
from desktop_bridge.world_simulation_handler import WorldSimulationHandler


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
    assert [plan["planId"] for plan in replay["presentation"]["plans"]] == [
        plan["planId"] for plan in repeated["presentation"]["plans"]
    ]
    performance_plan = replay["beats"][-1]["performancePlan"]
    assert performance_plan["schemaVersion"] == 1
    assert performance_plan["cues"][0]["kind"] == "dialogue"
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
    initial = world["presentation"]
    assert initial["session"]["status"] == "playing"
    assert len(initial["plans"]) == 1
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
    assert checkpoint["presentation"]["session"]["lastPresentedEventSequence"] == 1
    assert checkpoint["presentation"]["plans"] == []
    duplicate = handler.handle(
        "worlds.presentation.checkpoint",
        {"world_id": world["id"], "plan_id": plan_id, "cue_index": 0},
        request_id="duplicate-checkpoint",
    )
    assert duplicate == checkpoint

    handler._repository.delete_presentation_session(world["id"])
    handler.close()
    restarted = WorldSimulationHandler(workspace=tmp_path, role_store=role_store)
    rebuilt = restarted.handle(
        "worlds.get", {"world_id": world["id"]}, request_id="rebuild-session"
    )
    assert rebuilt is not None
    assert rebuilt["world"]["presentation"]["session"]["lastPresentedEventSequence"] == 0
    assert rebuilt["world"]["presentation"]["plans"]
    restarted.close()


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
    stored = handler._repository.get_draft(draft["draft"]["id"])
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
    stored = handler._repository.get_draft(draft["draft"]["id"])
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
    world = handler._repository.require_world(world_id)
    resident = handler._repository.list_residents(world_id)[0]
    run = handler._service.start_run(
        world_id,
        kind="action",
        request_id="visual-action:run",
        expected_revision=world.revision,
        random_seed="visual-action",
    )
    proposal = handler._proposal(
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
    handler._service.submit_action(proposal, request_id="visual-action")

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
