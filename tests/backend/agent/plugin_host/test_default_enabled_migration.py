"""Builtin manifests stay consistent with the default-enabled upgrade migration."""

from __future__ import annotations

from pathlib import Path

from agent.plugin_host.manifest import load_manifest

# Plugins that shipped already default-disabled do not belong on the upgrade
# migration: recording them would write enabled = true into old configs.
_DEFAULT_DISABLED_SINCE_BUILTIN = {
    "gpt_sovits_tts",
    "grok_bot",
    "herdr",
    "sensevoice_asr",
}


def test_builtin_default_disabled_plugins_match_the_upgrade_migration():
    """Only plugins that used to default on need the upgrade migration."""
    from agent.plugin_default_enabled_migration import DEFAULT_DISABLED_PLUGINS

    root = Path(__file__).resolve().parents[4] / "plugins"
    manifests = [load_manifest(path.parent) for path in root.glob("*/manifest.yaml")]
    default_disabled = {
        manifest.id
        for manifest in manifests
        if manifest
        and manifest.distribution == "builtin"
        and not manifest.default_enabled
    }
    assert not _DEFAULT_DISABLED_SINCE_BUILTIN & set(DEFAULT_DISABLED_PLUGINS)
    assert default_disabled - _DEFAULT_DISABLED_SINCE_BUILTIN == set(
        DEFAULT_DISABLED_PLUGINS
    )
    assert default_disabled == {
        "browser_use",
        "computer_use",
        "novelai",
        *_DEFAULT_DISABLED_SINCE_BUILTIN,
    }


def test_builtin_channel_plugins_are_grouped_as_channels():
    root = Path(__file__).resolve().parents[4] / "plugins"
    manifests = [load_manifest(path.parent) for path in root.glob("*/manifest.yaml")]
    assert manifests
    for manifest in manifests:
        assert manifest is not None
        if "channels" in manifest.capabilities:
            assert manifest.category == "channel", manifest.id
