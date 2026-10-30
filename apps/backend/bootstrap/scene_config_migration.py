"""Move ``[agent.scene_observation].enabled`` into ``[plugins.scene]``.

Only a missing ``observation_enabled`` is copied. The legacy table is deleted
after that edit succeeds. A later load finds no legacy table, so the move
does not run again and does not overwrite a value the plugin already stores.
A table this editor cannot locate raises and leaves the file unchanged.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from bootstrap.config_text_editor import plugin_table_editor
from shiori_sdk.files.text import atomic_save_text

SCENE_PLUGIN_ID = "scene"
OBSERVATION_ENABLED_KEY = "observation_enabled"
_UNLOCATABLE_MESSAGE = (
    "{path} 里的 agent.scene_observation 或 plugins.scene 写成了内联表或点分键，"
    "无法自动迁移；请先改成独立的 [agent.scene_observation] 与 [plugins.scene] 表"
)


def migrate_legacy_scene_config(path: Path) -> None:
    """Migrates ``path`` once. No legacy table means there is nothing to do."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    agent = data.get("agent")
    if not isinstance(agent, dict) or "scene_observation" not in agent:
        return
    enabled = _legacy_enabled(agent["scene_observation"])
    existing = _existing_plugin_values(data)
    editor = plugin_table_editor()
    updated = text
    if OBSERVATION_ENABLED_KEY not in existing:
        values = {**existing, OBSERVATION_ENABLED_KEY: enabled}
        try:
            updated = editor.merge_plugin_table(text, SCENE_PLUGIN_ID, values)
        except editor.PluginTableConflict as exc:
            raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path)) from exc
    updated = editor.remove_table(updated, ["agent", "scene_observation"])
    migrated = tomllib.loads(updated)
    migrated_agent = migrated.get("agent")
    if isinstance(migrated_agent, dict) and "scene_observation" in migrated_agent:
        raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path))
    if updated != text:
        atomic_save_text(path, updated)


def _legacy_enabled(raw: object) -> bool:
    """The old loader: omitted ``enabled`` is true; anything else is an error."""
    if not isinstance(raw, dict) or set(raw) - {"enabled"}:
        raise ValueError("agent.scene_observation only accepts enabled")
    if any(not isinstance(value, bool) for value in raw.values()):
        raise ValueError("agent.scene_observation switches must be boolean")
    return bool(raw.get("enabled", True))


def _existing_plugin_values(data: dict[str, Any]) -> dict[str, Any]:
    plugins = data.get("plugins")
    existing = plugins.get(SCENE_PLUGIN_ID) if isinstance(plugins, dict) else None
    return dict(existing) if isinstance(existing, dict) else {}
