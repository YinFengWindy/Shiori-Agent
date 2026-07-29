"""Resolve immutable world snapshot assets into renderer-facing plans."""

from __future__ import annotations

from typing import Any

from world_simulation.performance import PerformancePlan
from world_simulation.visuals import WorldVisualResolver
from world_simulation.world import NativeResident, RoleTemplateSnapshot


class WorldPresentationAssetResolver:
    """Enrich semantic sprite cues from world-owned role snapshots."""

    def __init__(
        self,
        *,
        snapshots: list[RoleTemplateSnapshot],
        residents: list[NativeResident],
    ) -> None:
        snapshots_by_id = {snapshot.id: snapshot for snapshot in snapshots}
        self._snapshots_by_actor = {
            actor_id: snapshot
            for resident in residents
            if (snapshot := snapshots_by_id.get(resident.snapshot_id)) is not None
            for actor_id in (resident.id, snapshot.source_role_id)
        }
        self._visuals = WorldVisualResolver()

    def to_bridge_dict(self, plan: PerformancePlan) -> dict[str, Any]:
        """Return one plan with trusted snapshot paths attached to sprite cues."""

        value = plan.to_bridge_dict()
        for cue in value["cues"]:
            if cue["kind"] != "sprites":
                continue
            payload = cue["payload"]
            items = payload.get("items") if isinstance(payload, dict) else None
            if isinstance(items, list):
                payload["items"] = [self._sprite(item) for item in items]
        return value

    def _sprite(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        item = dict(value)
        actor_id = str(item.get("actor_id") or item.get("actorId") or "").strip()
        snapshot = self._snapshots_by_actor.get(actor_id)
        if snapshot is None:
            return item
        mood = str(item.get("mood") or "").strip()
        resolved = self._visuals.resolve(snapshot, mood)
        if not resolved.asset_id or not resolved.path:
            return item

        item["assetId"] = resolved.asset_id
        item["image_path"] = resolved.path
        avatar = self._asset(
            snapshot, str(snapshot.visual_profile.get("avatar_asset_id") or "")
        )
        if avatar is not None and avatar["assetId"] != resolved.asset_id:
            item["fallbackIds"] = [avatar["assetId"]]
            item["fallbackAssets"] = [avatar]
        return item

    @staticmethod
    def _asset(snapshot: RoleTemplateSnapshot, asset_id: str) -> dict[str, str] | None:
        if not asset_id:
            return None
        asset = next(
            (
                item
                for item in snapshot.assets
                if isinstance(item, dict) and str(item.get("id") or "") == asset_id
            ),
            None,
        )
        path = str(asset.get("path") or "") if asset else ""
        return {"assetId": asset_id, "image_path": path} if path else None
