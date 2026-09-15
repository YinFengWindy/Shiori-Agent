"""Akasha config follows workspace storage for loading and initialization."""

import pytest

from plugins.akasha.backend.config import ensure_akasha_config_file, load_akasha_config


@pytest.mark.parametrize(
    "location", ["new", "workspace", "package", "old", "old-backend"]
)
def test_load_and_ensure_preserve_user_parameters_after_code_replacement(
    tmp_path, monkeypatch, location
):
    monkeypatch.setattr("agent.plugin_host.local_config.REPOSITORY_ROOT", tmp_path)
    workspace = tmp_path / "workspace"
    package = tmp_path / "plugins/akasha/backend"
    target = workspace / "plugin-data/akasha/config.local.toml"
    source = {
        "new": target,
        "workspace": workspace / "plugins/akasha/config.local.toml",
        "package": package / "config.local.toml",
        "old": tmp_path / "apps/backend/plugins/akasha/config.local.toml",
        "old-backend": tmp_path
        / "apps/backend/plugins/akasha/backend/config.local.toml",
    }[location]
    source.parent.mkdir(parents=True)
    source.write_text('db_path = "custom.db"\ndense_top_k = 23\n', encoding="utf-8")
    cfg = load_akasha_config(plugin_dir=package, workspace=workspace)
    assert cfg.db_path == "custom.db"
    assert cfg.dense_top_k == 23
    assert ensure_akasha_config_file(plugin_dir=package, workspace=workspace) == target
    package.mkdir(parents=True, exist_ok=True)
    (package / "config.local.toml").write_text("dense_top_k = 1\n", encoding="utf-8")
    assert load_akasha_config(plugin_dir=package, workspace=workspace) == cfg


def test_clean_install_only_creates_workspace_config(tmp_path):
    package = tmp_path / "install/akasha/backend"
    workspace = tmp_path / "workspace"
    target = ensure_akasha_config_file(plugin_dir=package, workspace=workspace)
    assert target == workspace / "plugin-data/akasha/config.local.toml"
    assert target.is_file()
    assert not package.exists()
    assert load_akasha_config(plugin_dir=package, workspace=workspace).dense_top_k == 10
