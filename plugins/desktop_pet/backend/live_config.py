"""Per-role live-chat settings kept in the pet's private files.

The room, the pause between replies and how long a danmaku may wait are the
user's settings; the queue capacity is an implementation constant. A saved
room takes effect at the next start; the timing reaches a running run at once.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.storage import plugin_data_dir

from .storage import PLUGIN_ID, safe_role_id

# User-facing explanation per field, used for every validation failure.
_FIELD_MESSAGES = {
    "room_id": "直播间号必须是正整数",
    "reply_interval_seconds": "回复间隔必须是 0–300 之间的整数秒",
    "wait_timeout_seconds": "等待时限必须是 5–600 之间的整数秒",
}


class LiveConfig(BaseModel):
    """One role's live settings."""

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

    def update(self, role_id: str, changes: dict[str, object]) -> LiveConfig:
        """Merge only the given fields into the stored settings and save.

        Raises ``ValueError`` with a Chinese message when a value is invalid;
        nothing is written then.
        """
        values = {**self.read(role_id).model_dump(), **changes}
        try:
            config = LiveConfig.model_validate(values)
        except ValidationError as error:
            raise ValueError(_explain(error)) from None
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


def _explain(error: ValidationError) -> str:
    messages: list[str] = []
    for item in error.errors():
        field = str(item["loc"][0]) if item["loc"] else ""
        message = _FIELD_MESSAGES.get(field, f"不支持的直播设置项: {field}")
        if message not in messages:
            messages.append(message)
    return "；".join(messages)
