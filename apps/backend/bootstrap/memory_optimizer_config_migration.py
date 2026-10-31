"""Move the memory optimizer settings into ``[plugins.memory_optimizer]``.

The old loader read ``memory_optimizer_enabled`` and
``memory_optimizer_interval_seconds`` from ``[agent.maintenance]``, falling
back to top-level keys of the same name. Values that differ from the plugin's
defaults move: ``memory_optimizer_enabled = false`` becomes ``enabled =
false`` (the plugin is disabled), and the interval becomes
``interval_seconds``, raised to the old minimum of 60. A key the plugin table
already has is kept. Then ``[agent.maintenance]`` and the top-level keys are
deleted, so a later load finds nothing to do.

The rewritten text must parse to exactly the expected document; a table or
key this editor cannot locate raises and leaves the file unchanged.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from bootstrap.config_text_editor import plugin_table_editor
from shiori_sdk.files.text import atomic_save_text

MEMORY_OPTIMIZER_PLUGIN_ID = "memory_optimizer"
INTERVAL_SECONDS_KEY = "interval_seconds"
# Host-owned enablement key, as in the memory migration.
_ENABLED_KEY = "enabled"
_LEGACY_ENABLED = "memory_optimizer_enabled"
_LEGACY_INTERVAL = "memory_optimizer_interval_seconds"
_LEGACY_KEYS = (_LEGACY_ENABLED, _LEGACY_INTERVAL)
# The plugin's defaults; the old loader's minimum interval.
_DEFAULT_INTERVAL_SECONDS = 64800
_MIN_INTERVAL_SECONDS = 60
_ROOT_KEY_RE = re.compile(
    r"^[ \t]*(?:memory_optimizer_enabled|memory_optimizer_interval_seconds)[ \t]*="
)
_UNLOCATABLE_MESSAGE = (
    "{path} 里的 agent.maintenance、顶层 memory_optimizer_* 或 plugins.memory_optimizer "
    "写成了内联表、点分键或引号键，无法自动迁移；请先改成独立的 [agent.maintenance] "
    "与 [plugins.memory_optimizer] 表"
)


_UNKNOWN_KEYS_MESSAGE = (
    "{path} 的 [agent.maintenance] 只能有 memory_optimizer_enabled 与 "
    "memory_optimizer_interval_seconds，无法自动迁移；请先删掉其他键"
)


def migrate_legacy_memory_optimizer_config(path: Path) -> None:
    """Migrates ``path`` once; nothing to do without the legacy keys."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    agent = data.get("agent")
    table = agent.get("maintenance") if isinstance(agent, dict) else None
    root_keys = [key for key in _LEGACY_KEYS if key in data]
    if table is None and not root_keys:
        return
    maintenance = _legacy_table(table, path) if table is not None else {}
    legacy = {key: maintenance.get(key, data.get(key)) for key in _LEGACY_KEYS}
    existing = _existing_plugin_values(data)
    values = {**_plugin_values(legacy), **existing}
    editor = plugin_table_editor()
    updated = text
    if values != existing:
        try:
            updated = editor.merge_plugin_table(
                text, MEMORY_OPTIMIZER_PLUGIN_ID, values
            )
        except editor.PluginTableConflict as exc:
            raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path)) from exc
    updated = editor.remove_table(updated, ["agent", "maintenance"])
    updated = _remove_root_keys(updated)
    if _without_empty_agent(tomllib.loads(updated)) != _expected_document(data, values):
        raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path))
    atomic_save_text(path, updated)


def _legacy_table(raw: object, path: Path) -> dict[str, Any]:
    """``[agent.maintenance]`` only ever held the two optimizer keys."""
    if not isinstance(raw, dict) or set(raw) - set(_LEGACY_KEYS):
        raise ValueError(_UNKNOWN_KEYS_MESSAGE.format(path=path))
    return raw


def _plugin_values(legacy: dict[str, Any]) -> dict[str, Any]:
    """The plugin keys whose legacy values differ from the plugin's defaults."""
    values: dict[str, Any] = {}
    enabled = legacy[_LEGACY_ENABLED]
    if enabled is not None:
        if not isinstance(enabled, bool):
            raise ValueError(f"{_LEGACY_ENABLED} 必须是布尔值")
        if not enabled:
            values[_ENABLED_KEY] = False
    interval = legacy[_LEGACY_INTERVAL]
    if interval is not None:
        if isinstance(interval, bool) or not isinstance(interval, int):
            raise ValueError(f"{_LEGACY_INTERVAL} 必须是整数")
        seconds = max(_MIN_INTERVAL_SECONDS, interval)
        if seconds != _DEFAULT_INTERVAL_SECONDS:
            values[INTERVAL_SECONDS_KEY] = seconds
    return values


def _remove_root_keys(text: str) -> str:
    """Drops the legacy key lines that come before the first table header."""
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith("["):
            kept.extend(lines[index:])
            break
        if not _ROOT_KEY_RE.match(line):
            kept.append(line)
    return "".join(kept)


def _expected_document(
    data: dict[str, Any], plugin_values: dict[str, Any]
) -> dict[str, Any]:
    """``data`` without the legacy keys and with the plugin table as migrated."""
    expected = {key: value for key, value in data.items() if key not in _LEGACY_KEYS}
    agent = expected.get("agent")
    if isinstance(agent, dict):
        expected["agent"] = {
            key: value for key, value in agent.items() if key != "maintenance"
        }
    if plugin_values:
        plugins = dict(expected.get("plugins") or {})
        plugins[MEMORY_OPTIMIZER_PLUGIN_ID] = plugin_values
        expected["plugins"] = plugins
    return _without_empty_agent(expected)


def _without_empty_agent(document: dict[str, Any]) -> dict[str, Any]:
    """An ``[agent]`` left empty parses the same as a removed one."""
    if document.get("agent") == {}:
        return {key: value for key, value in document.items() if key != "agent"}
    return document


def _existing_plugin_values(data: dict[str, Any]) -> dict[str, Any]:
    plugins = data.get("plugins")
    existing = (
        plugins.get(MEMORY_OPTIMIZER_PLUGIN_ID) if isinstance(plugins, dict) else None
    )
    return dict(existing) if isinstance(existing, dict) else {}
