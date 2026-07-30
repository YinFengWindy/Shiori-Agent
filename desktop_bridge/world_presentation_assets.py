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
        """Return one plan enriched with trusted snapshot presentation data."""

        value = plan.to_bridge_dict()
        for cue in value["cues"]:
            if cue["kind"] == "sprites":
                payload = cue["payload"]
                items = payload.get("items") if isinstance(payload, dict) else None
                if isinstance(items, list):
                    payload["items"] = [self._sprite(item) for item in items]
            elif cue["kind"] == "dialogue":
                payload = cue["payload"]
                cue["payload"] = self._dialogue(payload)
        return value

    def _dialogue(self, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        item = dict(value)
        item.pop("voiceProfile", None)
        item.pop("voice_profile", None)
        actor_id = str(item.get("actor_id") or item.get("actorId") or "").strip()
        snapshot = self._snapshots_by_actor.get(actor_id)
        if snapshot is None:
            return item
        voice_profile = self._voice_profile(snapshot, str(item.get("mood") or "").strip())
        if voice_profile is not None:
            item["voiceProfile"] = voice_profile
        return item

    @staticmethod
    def _voice_profile(snapshot: RoleTemplateSnapshot, mood: str) -> dict[str, Any] | None:
        profile = snapshot.voice_profile
        if not isinstance(profile, dict):
            return None
        voice_id = str(profile.get("voice_id") or "").strip()
        if not voice_id or profile.get("enabled") is False:
            return None

        raw_speed = profile.get("speed", 1.0)
        speed = float(raw_speed) if isinstance(raw_speed, (int, float)) else 1.0
        if not 0.5 <= speed <= 2.0:
            speed = 1.0
        raw_config_version = profile.get("config_version", 1)
        config_version = (
            raw_config_version
            if isinstance(raw_config_version, int) and not isinstance(raw_config_version, bool)
            else 1
        )
        raw_emotions = profile.get("mood_tts_emotions")
        emotions = raw_emotions if isinstance(raw_emotions, dict) else {}
        mood_emotions = {
            str(name).strip(): str(emotion).strip()
            for name, emotion in emotions.items()
            if str(name).strip() and str(emotion).strip()
        }
        return {
            "configVersion": config_version,
            "enabled": True,
            "provider": str(profile.get("provider") or "minimax").strip() or "minimax",
            "voiceId": voice_id,
            "speed": speed,
            "moodEmotions": mood_emotions,
            "emotion": mood_emotions.get(mood, ""),
        }

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
