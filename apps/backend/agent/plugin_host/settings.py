"""Configuration and process resources shared by one host plugin generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Mapping

from agent.plugin_host.discovery import TrustCheck
from agent.plugin_host.manifest import PluginManifest
from agent.plugin_host.reload import ProcessResourceSource

# The enable flag belongs to the host, in the plugin's existing config table.
PLUGIN_ENABLED_CONFIG_KEY = "enabled"


def plugin_enabled(manifest: PluginManifest, stored: Mapping[str, Any]) -> bool:
    """Returns whether a plugin is enabled given its ``[plugins.<id>]`` table.

    An explicit ``enabled`` always wins; without one the manifest's
    ``default_enabled`` decides. Shared by the kernel's load gate and the
    desktop plugin/channel listings so they can never disagree.
    """
    return bool(stored.get(PLUGIN_ENABLED_CONFIG_KEY, manifest.default_enabled))


@dataclass
class PluginGenerationSettings:
    """What one kernel generation itself runs on; services plugins use come from core.

    ``plugin_configs`` / ``raw_plugin_configs`` are the live ``[plugins.<id>]``
    tables: an in-generation reload or toggle swaps and rolls back entries in
    place. ``previously_active_plugins`` shrinks when a plugin is disabled
    within the generation, so a later re-enable is a fresh start.
    """

    # Execution identity and plugin KV root; None in host tests
    # without a workspace (a plugin declaring ``kv`` then fails before setup).
    workspace: Path | None = None
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw_plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # The process-level owner (PROCESSES). The generation retains attachments
    # across in-generation reloads; the app publishes the active generation.
    # The core hands each plugin its attachment.
    process_resources: ProcessResourceSource | None = None
    is_reload: bool = False
    previously_active_plugins: frozenset[str] = frozenset()
    # Live activation approval supplied by bootstrap; no checker means untrusted.
    is_trusted: TrustCheck | None = None
