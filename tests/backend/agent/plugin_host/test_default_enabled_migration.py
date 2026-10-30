"""Builtin manifests keep their declared default and category."""

from __future__ import annotations

from pathlib import Path

from agent.plugin_host.manifest import load_manifest


def test_builtin_default_disabled_plugins_are_the_declared_set():
    root = Path(__file__).resolve().parents[4] / "plugins"
    manifests = [load_manifest(path.parent) for path in root.glob("*/manifest.yaml")]
    default_disabled = {
        manifest.id
        for manifest in manifests
        if manifest
        and manifest.distribution == "builtin"
        and not manifest.default_enabled
    }
    assert default_disabled == {
        "browser_use",
        "computer_use",
        "grok_bot",
        "gpt_sovits_tts",
        "herdr",
        "mcp",
        "novelai",
        "sensevoice_asr",
    }


def test_builtin_channel_plugins_are_grouped_as_channels():
    root = Path(__file__).resolve().parents[4] / "plugins"
    manifests = [load_manifest(path.parent) for path in root.glob("*/manifest.yaml")]
    assert manifests
    for manifest in manifests:
        assert manifest is not None
        if manifest.channels:
            assert manifest.category == "channel", manifest.id
