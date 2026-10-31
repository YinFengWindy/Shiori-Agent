"""Move proactive settings out of the host tables the runtime no longer owns.

``[agent.proactive_strategies]`` ``scene_followup`` / ``relationship`` move
into ``[plugins.proactive]`` when they differ from the default (both on) and
the plugin table does not already have that key. The top-level ``[proactive]``
section has no runtime reader: it is deleted and logged, not copied. Then the
legacy tables are removed, so a later load finds nothing to do.

The rewritten text must parse to exactly the expected document. A table or
key this editor cannot locate raises and leaves the file unchanged.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from bootstrap.config_text_editor import plugin_table_editor
from shiori_sdk.files.text import atomic_save_text

logger = logging.getLogger(__name__)

PROACTIVE_PLUGIN_ID = "proactive"
_STRATEGY_KEYS = ("scene_followup", "relationship")
_UNLOCATABLE_MESSAGE = (
    "{path} 里的 agent.proactive_strategies、proactive 或 plugins.proactive "
    "写成了内联表、点分键或引号键，无法自动迁移；请先改成独立的 "
    "[agent.proactive_strategies]、[proactive] 与 [plugins.proactive] 表"
)
_UNKNOWN_KEYS_MESSAGE = (
    "{path} 的 [agent.proactive_strategies] 只能有 scene_followup 与 "
    "relationship，无法自动迁移；请先删掉其他键"
)


def migrate_legacy_proactive_config(path: Path) -> None:
    """Migrates ``path`` once. Nothing to do without a legacy table."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    agent = data.get("agent")
    has_strategies = isinstance(agent, dict) and "proactive_strategies" in agent
    has_section = "proactive" in data
    if not has_strategies and not has_section:
        return
    if has_section and not isinstance(data.get("proactive"), dict):
        raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path))
    legacy = (
        _legacy_strategies(agent["proactive_strategies"], path)
        if has_strategies and isinstance(agent, dict)
        else {}
    )
    _reject_unreadable_plugin_table(data, path)
    existing = _existing_plugin_values(data)
    values = {**_plugin_values(legacy), **existing}
    editor = plugin_table_editor()
    updated = text
    if values != existing:
        try:
            updated = editor.merge_plugin_table(text, PROACTIVE_PLUGIN_ID, values)
        except editor.PluginTableConflict as exc:
            raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path)) from exc
    updated = editor.remove_table(updated, ["agent", "proactive_strategies"])
    updated = editor.remove_table(updated, ["proactive"])
    try:
        migrated = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path)) from exc
    if _without_empty_agent(migrated) != _expected_document(data, values):
        raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path))
    if updated != text:
        atomic_save_text(path, updated)
    if has_section:
        logger.info("%s 的 [proactive] 段没有运行时消费方，已删除", path)


def _legacy_strategies(raw: object, path: Path) -> dict[str, Any]:
    """``[agent.proactive_strategies]`` only ever held the two switches."""
    if not isinstance(raw, dict) or set(raw) - set(_STRATEGY_KEYS):
        raise ValueError(_UNKNOWN_KEYS_MESSAGE.format(path=path))
    for key, value in raw.items():
        if not isinstance(value, bool):
            raise ValueError(
                f"{path} 的 [agent.proactive_strategies].{key} 必须是布尔值"
            )
    return raw


def _plugin_values(legacy: dict[str, Any]) -> dict[str, Any]:
    """Switches whose legacy value differs from the default (enabled)."""
    return {key: legacy[key] for key in _STRATEGY_KEYS if legacy.get(key) is False}


def _reject_unreadable_plugin_table(data: dict[str, Any], path: Path) -> None:
    plugins = data.get("plugins")
    if not isinstance(plugins, dict) or PROACTIVE_PLUGIN_ID not in plugins:
        return
    if not isinstance(plugins[PROACTIVE_PLUGIN_ID], dict):
        raise ValueError(_UNLOCATABLE_MESSAGE.format(path=path))


def _expected_document(
    data: dict[str, Any], plugin_values: dict[str, Any]
) -> dict[str, Any]:
    """``data`` without the legacy tables and with the plugin table as migrated."""
    expected = {key: value for key, value in data.items() if key != "proactive"}
    agent = expected.get("agent")
    if isinstance(agent, dict):
        expected["agent"] = {
            key: value for key, value in agent.items() if key != "proactive_strategies"
        }
    plugins_raw = data.get("plugins")
    had_plugin = isinstance(plugins_raw, dict) and PROACTIVE_PLUGIN_ID in plugins_raw
    if plugin_values or had_plugin:
        plugins = dict(expected.get("plugins") or {})
        plugins[PROACTIVE_PLUGIN_ID] = plugin_values
        expected["plugins"] = plugins
    return _without_empty_agent(expected)


def _without_empty_agent(document: dict[str, Any]) -> dict[str, Any]:
    """An ``[agent]`` left empty parses the same as a removed one."""
    if document.get("agent") == {}:
        return {key: value for key, value in document.items() if key != "agent"}
    return document


def _existing_plugin_values(data: dict[str, Any]) -> dict[str, Any]:
    plugins = data.get("plugins")
    existing = plugins.get(PROACTIVE_PLUGIN_ID) if isinstance(plugins, dict) else None
    return dict(existing) if isinstance(existing, dict) else {}
