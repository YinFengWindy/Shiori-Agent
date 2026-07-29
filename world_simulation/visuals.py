"""Resolve world-owned role visuals without reading mutable role configuration."""

from __future__ import annotations

from dataclasses import dataclass

from world_simulation.world import RoleTemplateSnapshot


@dataclass(frozen=True)
class ResolvedWorldVisual:
    """One resolved world-owned visual or the stable silhouette fallback."""

    asset_id: str | None
    path: str | None
    source: str


class WorldVisualResolver:
    """Resolve a mood from one frozen role snapshot with deterministic fallbacks."""

    def resolve(self, snapshot: RoleTemplateSnapshot, mood: str) -> ResolvedWorldVisual:
        """Resolve current mood, default mood, avatar, then a fixed silhouette."""

        profile = snapshot.visual_profile
        bindings = profile.get("mood_illustration_bindings", {})
        assets = {
            str(asset.get("id") or ""): str(asset.get("path") or "")
            for asset in snapshot.assets
            if isinstance(asset, dict)
        }
        requested = str(mood or "").strip()
        default_mood = str(profile.get("default_mood") or "").strip()
        for candidate, source in ((requested, "mood"), (default_mood, "default_mood")):
            asset_id = (
                str(bindings.get(candidate) or "") if isinstance(bindings, dict) else ""
            )
            path = assets.get(asset_id, "")
            if asset_id and path:
                return ResolvedWorldVisual(asset_id=asset_id, path=path, source=source)
        avatar_id = str(profile.get("avatar_asset_id") or "")
        avatar_path = assets.get(avatar_id, "")
        if avatar_id and avatar_path:
            return ResolvedWorldVisual(
                asset_id=avatar_id, path=avatar_path, source="avatar"
            )
        return ResolvedWorldVisual(asset_id=None, path=None, source="silhouette")
