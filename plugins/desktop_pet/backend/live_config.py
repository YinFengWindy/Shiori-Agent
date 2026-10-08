"""Per-role live-chat settings kept in the pet's private files.

The room, the pause between replies and how long a danmaku may wait are the
user's settings; the queue capacity is an implementation constant.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.storage import plugin_data_dir

from .storage import PLUGIN_ID, safe_role_id


class LiveConfig(BaseModel):
    """One role's live settings; every save replaces the whole document."""

    model_config = ConfigDict(extra="forbid", strict=True)
    # The id from the room URL (short or real); ``None`` until configured.
    room_id: int | None = Field(default=None, gt=0)
    # Pause after one reply's output ends before the next reply is generated.
    reply_interval_seconds: int = Field(default=5, ge=0, le=300)
    # A danmaku not picked up within this time after arrival is dropped.
    wait_timeout_seconds: int = Field(default=30, ge=5, le=600)


class LiveConfigStore:
    """Atomic per-role JSON files under the plugin data directory."""

    def __init__(self, workspace: Path) -> None:
        self.root = plugin_data_dir(workspace, PLUGIN_ID) / "live-configs"

    def read(self, role_id: str) -> LiveConfig:
        """Missing means defaults; a corrupt file stays an error."""
        return LiveConfig.model_validate(load_json(self._path(role_id), {}))

    def write(self, role_id: str, values: dict[str, object]) -> LiveConfig:
        """Validate the full document before replacing the stored one."""
        config = LiveConfig.model_validate(values)
        atomic_save_json(self._path(role_id), config.model_dump(mode="json"))
        return config

    def delete(self, role_id: str) -> None:
        """Forget this role's settings; idempotent."""
        self._path(role_id).unlink(missing_ok=True)

    def prune(self, role_ids: set[str]) -> None:
        """Delete settings of roles that no longer exist."""
        if not self.root.is_dir():
            return
        for path in self.root.glob("*.json"):
            if path.stem not in role_ids:
                path.unlink()

    def _path(self, role_id: str) -> Path:
        return self.root / f"{safe_role_id(role_id)}.json"
