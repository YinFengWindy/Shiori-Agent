"""Recoverable commit of configuration and associated role model selections."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.files.text import atomic_save_text

logger = logging.getLogger(__name__)


class ConfigTransaction:
    """Journals two fixed workspace files and restores interrupted commits on startup."""

    def __init__(self, config_path: Path, workspace: Path) -> None:
        self.config_path = config_path
        self.roles_path = workspace / "roles" / "roles.json"
        self.journal_path = workspace / ".runtime-config-transaction.json"

    def recover(self) -> None:
        """Restores the last committed files before runtime configuration is loaded."""
        journal = load_json(self.journal_path, domain="runtime.config")
        if journal is None:
            return
        if journal["state"] == "prepared":
            self._restore(self.config_path, journal["config_before"])
            self._restore(self.roles_path, journal["roles_before"])
        elif journal["state"] != "committed":
            raise ValueError("runtime configuration journal state is invalid")
        self.journal_path.unlink()

    def commit(self, config_toml: str, roles_payload: dict | None = None) -> None:
        """Commits both files or restores both originals before propagating failure."""
        if self.journal_path.exists():
            journal = load_json(self.journal_path, domain="runtime.config")
            if journal["state"] == "committed":
                self.journal_path.unlink()
            else:
                raise RuntimeError(
                    "runtime configuration requires transaction recovery"
                )
        journal = {
            "state": "prepared",
            "config_before": self._read(self.config_path),
            "roles_before": self._read(self.roles_path),
        }
        atomic_save_json(self.journal_path, journal, domain="runtime.config")
        try:
            atomic_save_text(self.config_path, config_toml)
            if roles_payload is not None:
                atomic_save_text(
                    self.roles_path,
                    json.dumps(roles_payload, ensure_ascii=False, indent=2),
                )
            atomic_save_json(
                self.journal_path,
                {**journal, "state": "committed"},
                domain="runtime.config",
            )
        except BaseException:
            self._restore(self.config_path, journal["config_before"])
            self._restore(self.roles_path, journal["roles_before"])
            self.journal_path.unlink(missing_ok=True)
            raise
        # A committed journal is also a valid startup state. Cleanup failure must
        # not turn an already durable commit into an apparent apply failure.
        try:
            self.journal_path.unlink()
        except OSError as error:
            logger.warning(
                "Committed configuration journal cleanup deferred: %s", error
            )

    @staticmethod
    def _read(path: Path) -> str | None:
        return path.read_text(encoding="utf-8") if path.exists() else None

    @staticmethod
    def _restore(path: Path, content: str | None) -> None:
        if content is None:
            path.unlink(missing_ok=True)
        else:
            atomic_save_text(path, content)
