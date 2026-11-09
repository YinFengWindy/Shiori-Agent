"""Desktop-pet package metadata and per-role state, owned by the plugin."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from shiori_sdk.values import normalize_rel_path, now_iso


@dataclass(frozen=True)
class RolePetPackage:
    """A validated Codex-compatible pet package owned by one role."""

    id: str
    format: str
    display_name: str
    manifest_path: str
    spritesheet_path: str
    imported_at: str
    preview_path: str | None = None
    actions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes validated package metadata in the plugin namespace."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RolePetPackage":
        """Restores package metadata and normalizes workspace-relative asset paths."""
        package_id = str(payload.get("id") or "").strip()
        display_name = str(payload.get("display_name") or "").strip()
        manifest_path = normalize_rel_path(str(payload.get("manifest_path") or ""))
        spritesheet_path = normalize_rel_path(
            str(payload.get("spritesheet_path") or "")
        )
        if (
            not package_id
            or not display_name
            or not manifest_path
            or not spritesheet_path
        ):
            raise ValueError("桌宠包元数据不完整")
        raw_actions = payload.get("actions", {})
        actions = (
            {
                str(name).strip(): str(state).strip()
                for name, state in raw_actions.items()
                if str(name).strip() and str(state).strip()
            }
            if isinstance(raw_actions, dict)
            else {}
        )
        return cls(
            id=package_id,
            format=str(payload.get("format") or "").strip(),
            display_name=display_name,
            manifest_path=manifest_path,
            spritesheet_path=spritesheet_path,
            imported_at=str(payload.get("imported_at") or now_iso()),
            preview_path=normalize_rel_path(payload.get("preview_path")),
            actions=actions,
        )
