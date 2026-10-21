"""NovelAI's generation data root."""

from __future__ import annotations

from pathlib import Path

from shiori_sdk.storage import plugin_data_dir


def storage_root(workspace: Path) -> Path:
    """Return the plugin-owned directory for generated images and records."""
    return plugin_data_dir(workspace, "novelai") / "generation"
