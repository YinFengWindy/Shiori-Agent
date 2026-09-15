"""Host-owned persisted approvals of exact workspace package contents."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from infra.persistence.text_store import atomic_save_text


class PluginTrustStore:
    """Atomically persists explicit approvals outside plugin-owned directories."""

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "private_runtime" / "plugin-trust.json"

    def _read(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("插件信任记录格式无效")
        approvals = data.get("approvals")
        if not isinstance(approvals, dict):
            raise ValueError("插件信任记录内容无效")
        validated: dict[str, dict[str, str]] = {}
        for key, value in approvals.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValueError("插件信任记录内容无效")
            fingerprint, session = value.get("fingerprint"), value.get(
                "approved_session"
            )
            if (
                not isinstance(fingerprint, str)
                or re.fullmatch(r"[a-f0-9]{64}", fingerprint) is None
                or not isinstance(session, str)
            ):
                raise ValueError("插件信任记录内容无效")
            validated[key] = {"fingerprint": fingerprint, "approved_session": session}
        return validated

    def is_trusted(
        self, directory: Path, fingerprint: str, *, activation: bool = False
    ) -> bool:
        """Approval requires the exact candidate path and content identity."""
        approval = self._read().get(str(directory.absolute()))
        if approval is None or approval["fingerprint"] != fingerprint:
            return False
        session = os.environ.get("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "")
        # A bridge restart is not an app restart. Only a new desktop session may
        # activate approvals created by this session's confirmation dialog.
        return not (activation and session and approval["approved_session"] == session)

    def approve(self, directory: Path, fingerprint: str) -> None:
        """Replace one approval while preserving other packages and prior file on failure."""
        approvals = self._read()
        approvals[str(directory.absolute())] = {
            "fingerprint": fingerprint,
            "approved_session": os.environ.get(
                "SHIORI_DESKTOP_APPLICATION_SESSION_ID", ""
            ),
        }
        atomic_save_text(
            self.path,
            json.dumps(
                {"version": 1, "approvals": approvals}, ensure_ascii=False, indent=2
            )
            + "\n",
        )
