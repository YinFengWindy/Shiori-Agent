"""World-owned role snapshot construction for the desktop bridge."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from core.roles import RoleStore
from world_simulation.world import RoleTemplateSnapshot

_SNAPSHOT_CHARACTER_CANVAS = (1200, 1600)
_SNAPSHOT_CHARACTER_BASELINE = 1520
_SNAPSHOT_CHARACTER_MARGIN = 60


class WorldSnapshotBuilder:
    """Freeze role-owned visuals and voice metadata into world-owned assets."""

    def __init__(self, role_store: RoleStore, world_assets_dir: Path) -> None:
        self._roles = role_store
        self._world_assets_dir = world_assets_dir

    def snapshot_for(self, role: Any) -> RoleTemplateSnapshot:
        """Build one immutable role snapshot for a new world draft."""

        snapshot_id = f"snapshot-{uuid4().hex}"
        asset_ids: dict[str, str] = {}
        assets = []
        for source in [role.avatar, *role.illustrations]:
            if not source or source in asset_ids:
                continue
            copied = self._copy_snapshot_asset(snapshot_id, source)
            if copied is None:
                continue
            asset_id = f"asset-{uuid4().hex}"
            asset_ids[source] = asset_id
            assets.append({"id": asset_id, "path": copied})
        runtime = role.runtime_config if isinstance(role.runtime_config, dict) else {}
        raw_bindings = runtime.get("mood_illustration_bindings", {})
        bindings = raw_bindings if isinstance(raw_bindings, dict) else {}
        mood_bindings = {
            str(mood).strip(): asset_ids[str(path).strip()]
            for mood, path in bindings.items()
            if str(mood).strip() and str(path).strip() in asset_ids
        }
        raw_catalog = runtime.get("mood_catalog", [])
        catalog = raw_catalog if isinstance(raw_catalog, list) else []
        mood_catalog = [
            str(mood).strip() for mood in catalog if str(mood).strip() in mood_bindings
        ]
        default_mood = str(runtime.get("default_mood") or "").strip()
        if default_mood not in mood_bindings:
            default_mood = (
                mood_catalog[0] if mood_catalog else next(iter(mood_bindings), "")
            )
        return RoleTemplateSnapshot(
            id=snapshot_id,
            source_role_id=role.id,
            source_version=role.updated_at,
            persona={"name": role.name, "description": role.description},
            system_constraints=(role.system_prompt,),
            visual_profile={
                "default_mood": default_mood,
                "mood_catalog": mood_catalog,
                "mood_illustration_bindings": mood_bindings,
                "avatar_asset_id": asset_ids.get(role.avatar),
            },
            voice_profile=self._voice_profile(runtime),
            assets=tuple(assets),
        )

    def source_asset_path(self, relative_path: str | None) -> str | None:
        """Resolve a role-owned source asset for draft-only identity metadata."""

        return (
            str((self._roles.roles_dir / relative_path).resolve())
            if relative_path
            else None
        )

    def _copy_snapshot_asset(self, snapshot_id: str, relative_path: str) -> str | None:
        """Copy a role-owned asset before the source role can change or disappear."""

        source = (self._roles.roles_dir / relative_path).resolve()
        try:
            source.relative_to(self._roles.assets_dir.resolve())
        except ValueError:
            return None
        if not source.is_file():
            return None
        destination_dir = self._world_assets_dir / snapshot_id
        destination = destination_dir / f"{uuid4().hex}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._normalize_snapshot_character(source, destination)
        except (UnidentifiedImageError, OSError):
            destination = destination_dir / f"{uuid4().hex}{source.suffix}"
            shutil.copy2(source, destination)
        return str(destination.resolve())

    @staticmethod
    def _normalize_snapshot_character(source: Path, destination: Path) -> None:
        """Place visible character pixels on one transparent canvas and foot baseline."""

        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGBA")
            bounds = image.getchannel("A").getbbox()
            canvas = Image.new("RGBA", _SNAPSHOT_CHARACTER_CANVAS, (0, 0, 0, 0))
            if bounds is None:
                canvas.save(destination, format="PNG")
                return
            character = image.crop(bounds)
            max_width = _SNAPSHOT_CHARACTER_CANVAS[0] - 2 * _SNAPSHOT_CHARACTER_MARGIN
            max_height = _SNAPSHOT_CHARACTER_BASELINE - _SNAPSHOT_CHARACTER_MARGIN
            scale = min(1.0, max_width / character.width, max_height / character.height)
            if scale < 1.0:
                character = character.resize(
                    (
                        max(1, round(character.width * scale)),
                        max(1, round(character.height * scale)),
                    ),
                    Image.Resampling.LANCZOS,
                )
            x = (_SNAPSHOT_CHARACTER_CANVAS[0] - character.width) // 2
            y = _SNAPSHOT_CHARACTER_BASELINE - character.height
            canvas.alpha_composite(character, (x, y))
            canvas.save(destination, format="PNG")

    @staticmethod
    def _voice_profile(runtime: dict[str, Any]) -> dict[str, Any]:
        """Freeze only non-secret voice fields required by later presentation work."""

        raw_tts = runtime.get("tts", {})
        tts = raw_tts if isinstance(raw_tts, dict) else {}
        voice_id = str(tts.get("voice_id") or "").strip()
        if not voice_id:
            return {}
        speed = tts.get("speed", 1.0)
        normalized_speed = float(speed) if isinstance(speed, (int, float)) else 1.0
        if not 0.5 <= normalized_speed <= 2.0:
            normalized_speed = 1.0
        raw_emotions = tts.get("mood_tts_emotions", {})
        emotions = raw_emotions if isinstance(raw_emotions, dict) else {}
        return {
            "config_version": 1,
            "enabled": tts.get("enabled", True) is not False,
            "provider": str(tts.get("provider") or "minimax").strip() or "minimax",
            "voice_id": voice_id,
            "speed": normalized_speed,
            "mood_tts_emotions": {
                str(mood).strip(): str(emotion).strip()
                for mood, emotion in emotions.items()
                if str(mood).strip() and str(emotion).strip()
            },
        }
