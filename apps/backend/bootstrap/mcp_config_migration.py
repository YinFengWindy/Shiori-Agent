"""Enables the ``mcp`` plugin once for workspaces that already use MCP servers.

Before P6a the core reconnected every server in ``<workspace>/mcp_servers.json``
on each start. The ``mcp`` plugin is off by default, so an upgraded workspace
would lose those tools silently. When the file lists at least one server and
``[plugins.mcp]`` has no explicit ``enabled``, ``enabled = true`` is written
once. Any explicit ``enabled``, true or false, is the user's choice and is
left alone; after the write a later load finds it and does nothing. A new
install's empty server list stays off. A table this editor cannot locate
raises and leaves the file unchanged.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from bootstrap.config_text_editor import plugin_table_editor
from shiori_sdk.files.text import atomic_save_text

MCP_PLUGIN_ID = "mcp"
MCP_SERVERS_FILE = "mcp_servers.json"
# Host-owned enablement key, as in the memory migration.
_ENABLED_KEY = "enabled"
_UNLOCATABLE_MESSAGE = (
    "{path} 里的 plugins.mcp 写成了内联表或点分键，无法自动启用 MCP 插件；"
    "请先改成独立的 [plugins.mcp] 表"
)


def migrate_mcp_enabled(config_path: Path, workspace: Path) -> None:
    """Writes ``[plugins.mcp].enabled = true`` once, under the conditions above."""
    if not config_path.is_file() or not _has_servers(workspace / MCP_SERVERS_FILE):
        return
    text = config_path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    existing = _existing_plugin_values(data)
    if _ENABLED_KEY in existing:
        return
    editor = plugin_table_editor()
    try:
        updated = editor.merge_plugin_table(
            text, MCP_PLUGIN_ID, {**existing, _ENABLED_KEY: True}
        )
    except editor.PluginTableConflict as exc:
        raise ValueError(_UNLOCATABLE_MESSAGE.format(path=config_path)) from exc
    atomic_save_text(config_path, updated)


def _has_servers(path: Path) -> bool:
    """Whether the saved server list is non-empty, read as the plugin reads it."""
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # The plugin logs this file as unreadable and connects nothing.
        return False
    servers = data.get("servers") if isinstance(data, dict) else None
    return isinstance(servers, dict) and bool(servers)


def _existing_plugin_values(data: dict[str, Any]) -> dict[str, Any]:
    plugins = data.get("plugins")
    existing = plugins.get(MCP_PLUGIN_ID) if isinstance(plugins, dict) else None
    return dict(existing) if isinstance(existing, dict) else {}
