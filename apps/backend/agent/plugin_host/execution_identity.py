"""Keep already executed external code fixed across desktop bridge reconnects."""

from __future__ import annotations

import json
import os
from pathlib import Path

from shiori_sdk.files.text import atomic_save_text

from shiori_sdk.kernel import PackageContractError


class PluginExecutionIdentity:
    """Remember the first executed package per ID for one Electron application."""

    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "private_runtime" / "plugin-executions.json"

    def _read(self) -> dict[str, dict[str, str]]:
        session = os.environ.get("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "")
        if not session or not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError("插件执行记录格式无效")
        if value.get("session") != session:
            return {}
        packages = value.get("packages")
        if not isinstance(packages, dict) or any(
            not isinstance(key, str)
            or not isinstance(row, dict)
            or set(row) != {"directory", "fingerprint"}
            or any(not isinstance(item, str) for item in row.values())
            for key, row in packages.items()
        ):
            raise ValueError("插件执行记录内容无效")
        return packages

    def matches(self, plugin_id: str, directory: Path, fingerprint: str) -> bool:
        """A never executed package is eligible; an executed ID keeps its exact bytes."""
        packages = self._read()
        identity = {
            "directory": str(directory.absolute()),
            "fingerprint": fingerprint,
        }
        return all(
            row == identity
            for key, row in packages.items()
            if key == plugin_id or row["directory"] == identity["directory"]
        )

    def verify(self, plugin_id: str, directory: Path, fingerprint: str) -> None:
        """Raises ``executed_content_changed`` unless ``matches``; records nothing."""
        if not self.matches(plugin_id, directory, fingerprint):
            raise PackageContractError(
                "executed_content_changed",
                "content",
                "此插件已在本次运行执行过其他内容，请重启 Shiori 后重新确认",
            )

    def record(self, plugin_id: str, directory: Path, fingerprint: str) -> None:
        """Persist before import, including failed imports that may have had effects."""
        session = os.environ.get("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "")
        if not session:
            return
        packages = self._read()
        identity = {"directory": str(directory.absolute()), "fingerprint": fingerprint}
        previous = packages.get(plugin_id)
        self.verify(plugin_id, directory, fingerprint)
        if previous == identity:
            return
        packages[plugin_id] = identity
        atomic_save_text(
            self.path,
            json.dumps(
                {"version": 1, "session": session, "packages": packages},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
