from world_simulation.performance import compile_performance_plan
from world_simulation.timeline import TimelineEvent
from world_simulation.world import NativeResident, RoleTemplateSnapshot

from desktop_bridge.world_presentation_assets import WorldPresentationAssetResolver


def test_resolver_enriches_semantic_mood_with_avatar_fallback():
    snapshot = RoleTemplateSnapshot(
        id="snapshot-1",
        source_role_id="role-1",
        source_version="v1",
        persona={},
        visual_profile={
            "default_mood": "平静",
            "mood_illustration_bindings": {"平静": "asset-mood"},
            "avatar_asset_id": "asset-avatar",
        },
        assets=(
            {"id": "asset-mood", "path": "C:/world-assets/mood.png"},
            {"id": "asset-avatar", "path": "C:/world-assets/avatar.png"},
        ),
    )
    plan = compile_performance_plan(
        TimelineEvent(
            id="event-1",
            world_id="world-1",
            event_type="scene.action.committed",
            effective_at="2026-07-29T10:00:00+00:00",
            sequence=1,
            changes={
                "presentation": {
                    "sprites": [{"actor_id": "resident-1", "mood": "警觉"}]
                }
            },
        )
    )
    resolver = WorldPresentationAssetResolver(
        snapshots=[snapshot],
        residents=[NativeResident(id="resident-1", snapshot_id=snapshot.id, name="凛")],
    )

    sprite = resolver.to_bridge_dict(plan)["cues"][0]["payload"]["items"][0]

    assert sprite["assetId"] == "asset-mood"
    assert sprite["image_path"] == "C:/world-assets/mood.png"
    assert sprite["fallbackIds"] == ["asset-avatar"]
    assert sprite["fallbackAssets"] == [
        {
            "assetId": "asset-avatar",
            "image_path": "C:/world-assets/avatar.png",
        }
    ]


def _dialogue_plan(payload: dict[str, object]):
    return compile_performance_plan(
        TimelineEvent(
            id="event-dialogue",
            world_id="world-1",
            event_type="scene.dialogue.committed",
            effective_at="2026-07-29T10:00:00+00:00",
            sequence=1,
            changes={"presentation": {"dialogue": payload}},
        )
    )


def _voice_snapshot(**voice_profile: object) -> RoleTemplateSnapshot:
    return RoleTemplateSnapshot(
        id="snapshot-voice",
        source_role_id="role-voice",
        source_version="v1",
        persona={},
        voice_profile=voice_profile,
    )


def test_resolver_projects_safe_voice_profile_and_mood_emotion():
    plan = _dialogue_plan(
        {
            "actor_id": "resident-voice",
            "mood": "开心",
            "content": "你好。",
            "voiceProfile": {"secret_key": "must-not-pass"},
        }
    )
    resolver = WorldPresentationAssetResolver(
        snapshots=[
            _voice_snapshot(
                config_version=1,
                enabled=True,
                provider="minimax",
                voice_id="rin-voice",
                speed=1.2,
                mood_tts_emotions={"开心": "happy", "悲伤": "sad"},
                secret_key="must-not-pass",
            )
        ],
        residents=[
            NativeResident(id="resident-voice", snapshot_id="snapshot-voice", name="凛")
        ],
    )

    dialogue = resolver.to_bridge_dict(plan)["cues"][0]["payload"]

    assert dialogue["voiceProfile"] == {
        "configVersion": 1,
        "enabled": True,
        "provider": "minimax",
        "voiceId": "rin-voice",
        "speed": 1.2,
        "moodEmotions": {"开心": "happy", "悲伤": "sad"},
        "emotion": "happy",
    }
    assert "secret_key" not in str(dialogue)


def test_resolver_does_not_project_voice_profile_without_actor_or_voice_id():
    resolver = WorldPresentationAssetResolver(
        snapshots=[_voice_snapshot(enabled=True, voice_id="")],
        residents=[
            NativeResident(id="resident-voice", snapshot_id="snapshot-voice", name="凛")
        ],
    )

    without_actor = resolver.to_bridge_dict(_dialogue_plan({"content": "无声线。"}))
    without_voice_id = resolver.to_bridge_dict(
        _dialogue_plan({"actorId": "resident-voice", "content": "无声线。"})
    )

    assert "voiceProfile" not in without_actor["cues"][0]["payload"]
    assert "voiceProfile" not in without_voice_id["cues"][0]["payload"]


def test_resolver_does_not_project_disabled_voice_profile():
    plan = _dialogue_plan({"actorId": "resident-voice", "mood": "平静"})
    resolver = WorldPresentationAssetResolver(
        snapshots=[
            _voice_snapshot(enabled=False, voice_id="rin-voice", secret_key="must-not-pass")
        ],
        residents=[
            NativeResident(id="resident-voice", snapshot_id="snapshot-voice", name="凛")
        ],
    )

    dialogue = resolver.to_bridge_dict(plan)["cues"][0]["payload"]

    assert "voiceProfile" not in dialogue
    assert "secret_key" not in str(dialogue)
