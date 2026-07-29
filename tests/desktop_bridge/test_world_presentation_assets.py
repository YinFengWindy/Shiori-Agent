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
