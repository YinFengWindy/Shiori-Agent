from world_simulation.visuals import WorldVisualResolver
from world_simulation.world import RoleTemplateSnapshot


def test_visual_resolver_uses_mood_default_avatar_then_silhouette():
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
    resolver = WorldVisualResolver()

    assert resolver.resolve(snapshot, "平静").source == "mood"
    assert resolver.resolve(snapshot, "悲伤").source == "default_mood"
    assert (
        resolver.resolve(
            RoleTemplateSnapshot(
                id="snapshot-2",
                source_role_id="role-1",
                source_version="v1",
                persona={},
                visual_profile={"avatar_asset_id": "asset-avatar"},
                assets=({"id": "asset-avatar", "path": "C:/world-assets/avatar.png"},),
            ),
            "悲伤",
        ).source
        == "avatar"
    )
    assert (
        resolver.resolve(
            RoleTemplateSnapshot(
                id="snapshot-3",
                source_role_id="role-1",
                source_version="v1",
                persona={},
            ),
            "悲伤",
        ).source
        == "silhouette"
    )
