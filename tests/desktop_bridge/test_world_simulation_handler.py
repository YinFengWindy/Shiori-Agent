from __future__ import annotations

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
