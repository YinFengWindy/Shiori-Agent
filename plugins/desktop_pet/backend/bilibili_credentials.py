"""Bilibili login credentials kept in the pet's private files, one per role.

They never enter the role extension projection, so role payloads, exports and
the renderer never carry the cookies.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.storage import plugin_data_dir

from .storage import PLUGIN_ID, safe_role_id


class BilibiliCredentials(BaseModel):
    """Cookies and identity captured by one confirmed QR login."""

    model_config = ConfigDict(extra="forbid", strict=True)
    uid: int
    uname: str
    cookies: dict[str, str] = Field(min_length=1)
    # Kept for a future cookie refresh; nothing consumes it yet.
    refresh_token: str


class BilibiliCredentialStore:
    """Atomic per-role credential files under the plugin data directory."""

    def __init__(self, workspace: Path) -> None:
        self.root = plugin_data_dir(workspace, PLUGIN_ID) / "bilibili-logins"

    def read(self, role_id: str) -> BilibiliCredentials | None:
        """Missing means logged out; a corrupt file stays an error."""
        value = load_json(self._path(role_id))
        return None if value is None else BilibiliCredentials.model_validate(value)

    def write(self, role_id: str, credentials: BilibiliCredentials) -> None:
        """Replace this role's credentials, owner-only on POSIX.

        The 0o700 directory also covers the atomic writer's temporary file;
        Windows keeps the profile directory's inherited ACL.
        """
        path = self._path(role_id)
        if os.name == "posix":
            self.root.mkdir(parents=True, exist_ok=True)
            self.root.chmod(0o700)
        atomic_save_json(path, credentials.model_dump(mode="json"))
        if os.name == "posix":
            path.chmod(0o600)

    def delete(self, role_id: str) -> None:
        """Forget this role's credentials; idempotent."""
        self._path(role_id).unlink(missing_ok=True)

    def prune(self, role_ids: set[str]) -> None:
        """Delete credentials of roles that no longer exist."""
        if not self.root.is_dir():
            return
        for path in self.root.glob("*.json"):
            if path.stem not in role_ids:
                path.unlink()

    def _path(self, role_id: str) -> Path:
        return self.root / f"{safe_role_id(role_id)}.json"
