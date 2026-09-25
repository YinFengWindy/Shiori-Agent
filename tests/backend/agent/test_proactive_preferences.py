"""Legacy preferences migrate once without changing unrelated proactive paths."""

import tomllib
import pytest
from agent.config import load_config, load_config_text
from agent.proactive_preferences import migrate_proactive_preferences


@pytest.fixture(autouse=True)
def _without_default_disabled_pinning(monkeypatch):
    """本文件只测自己的迁移：停掉默认停用插件与全局主动推送目标的升级迁移，免得它们改写测试配置。"""
    monkeypatch.setattr(
        "agent.plugin_default_enabled_migration.DEFAULT_DISABLED_PLUGINS", ()
    )
    monkeypatch.setattr(
        "agent.proactive_target_migration.remove_proactive_target",
        lambda _path, data: data,
    )


@pytest.mark.parametrize("location", ["plugins", "apps/backend/plugins"])
def test_marker_migration_preserves_defaults_and_is_idempotent(
    tmp_path, monkeypatch, location
):
    import agent.proactive_preferences as module

    monkeypatch.setattr(module, "resource_root", lambda: tmp_path)
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path)
    marker = tmp_path / location / "relationship_proactive" / "plugin.disabled"
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")
    path = tmp_path / "config.toml"
    path.write_text("# keep me\n[agent]\nmax_tokens = 123\n", encoding="utf-8")
    config = load_config(path)
    assert config.proactive_strategies.scene_followup is False
    assert config.proactive_strategies.relationship is False
    assert config.max_tokens == 123
    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert marker.exists()
    load_config(path)
    assert path.read_text(encoding="utf-8") == text
    path.write_text(
        text.replace("relationship = false", "relationship = true"), encoding="utf-8"
    )
    assert load_config(path).proactive_strategies.relationship is True


def test_explicit_core_values_win_and_other_proactive_paths_stay_enabled(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[proactive]\nprofile = "daily"\nenabled = true\n[proactive.drift]\nenabled = true\n[plugins.relationship_proactive]\nenabled = false\n[agent.proactive_strategies]\nscene_followup = true\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.proactive_strategies.scene_followup is True
    assert config.proactive_strategies.relationship is False
    assert config.proactive.enabled is True
    assert config.proactive.drift_enabled is True


def test_no_legacy_setting_keeps_both_enabled_without_file_write(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[agent]\nmax_tokens = 123\n", encoding="utf-8")
    before = path.read_bytes()
    assert load_config(path).proactive_strategies.relationship
    assert path.read_bytes() == before


def test_candidate_validation_preserves_legacy_disable_without_persistence():
    config = load_config_text("[plugins.relationship_proactive]\nenabled = false\n")
    assert not config.proactive_strategies.relationship
    assert not config.proactive_strategies.scene_followup


def test_failed_migration_retains_source(tmp_path, monkeypatch):
    from pathlib import Path

    path = tmp_path / "config.toml"
    original = "[plugins.relationship_proactive]\nenabled = false\n"
    path.write_text(original, encoding="utf-8")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        migrate_proactive_preferences(path, tomllib.loads(original))
    assert path.read_text(encoding="utf-8") == original
    assert sorted(item.name for item in tmp_path.iterdir()) == ["config.toml"]


@pytest.mark.parametrize("value", ['"false"', "123"])
def test_strategy_switch_requires_boolean(value):
    with pytest.raises(ValueError, match="boolean"):
        load_config_text(f"[agent.proactive_strategies]\nrelationship = {value}\n")
