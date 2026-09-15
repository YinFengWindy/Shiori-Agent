"""Shared local TOML migration covers old layouts and read-only installation code."""

from pathlib import Path

import pytest

import agent.plugin_host.local_config as local_config


@pytest.mark.parametrize(
    "source_location", ["workspace", "package", "old", "old-backend"]
)
def test_migrates_each_old_layout_and_ensure_uses_same_path(
    tmp_path, monkeypatch, source_location
):
    workspace = tmp_path / "workspace"
    package = tmp_path / "checkout/plugins/demo/backend"
    monkeypatch.setattr(local_config, "REPOSITORY_ROOT", tmp_path / "checkout")
    sources = {
        "workspace": workspace / "plugins/demo/config.local.toml",
        "package": package / "config.local.toml",
        "old": tmp_path / "checkout/apps/backend/plugins/demo/config.local.toml",
        "old-backend": tmp_path
        / "checkout/apps/backend/plugins/demo/backend/config.local.toml",
    }
    source = sources[source_location]
    source.parent.mkdir(parents=True)
    source.write_text('db_path = "kept.db"\n', encoding="utf-8")
    kwargs = {"workspace": workspace, "plugin_dir": package, "plugin_id": "demo"}
    target = local_config.resolve_local_config(**kwargs)
    assert target == workspace / "plugin-data/demo/config.local.toml"
    assert not source.exists()
    assert local_config.resolve_local_config(**kwargs, default_text="") == target
    assert target.read_text(encoding="utf-8") == 'db_path = "kept.db"\n'
    assert not (package / "config.local.toml").exists()


@pytest.mark.parametrize("target_exists", [False, True])
def test_workspace_override_beats_package_and_unused_sources_survive(
    tmp_path, monkeypatch, target_exists
):
    monkeypatch.setattr(local_config, "REPOSITORY_ROOT", tmp_path)
    workspace = tmp_path / "workspace"
    package = tmp_path / "plugins/demo/backend"
    files = [
        workspace / "plugin-data/demo/config.local.toml",
        workspace / "plugins/demo/config.local.toml",
        package / "config.local.toml",
    ]
    for index, file in enumerate(files):
        if index or target_exists:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(f"value = {index}\n", encoding="utf-8")
    target = local_config.resolve_local_config(
        workspace=workspace, plugin_dir=package, plugin_id="demo"
    )
    assert (
        target.read_text(encoding="utf-8") == f"value = {0 if target_exists else 1}\n"
    )
    assert files[1].exists() is target_exists
    assert files[2].exists()


def test_failed_toml_write_leaves_source_and_retry_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(local_config, "REPOSITORY_ROOT", tmp_path)
    package = tmp_path / "plugins/demo/backend"
    package.mkdir(parents=True)
    source = package / "config.local.toml"
    source.write_text('db_path = "keep.db"\n', encoding="utf-8")
    kwargs = {
        "workspace": tmp_path / "workspace",
        "plugin_dir": package,
        "plugin_id": "demo",
    }

    def fail(*args):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr("infra.persistence.text_store.atomic_save_text", fail)
        with pytest.raises(OSError, match="disk full"):
            local_config.resolve_local_config(**kwargs)
    assert source.read_text(encoding="utf-8") == 'db_path = "keep.db"\n'
    assert not (tmp_path / "workspace/plugin-data/demo/config.local.toml").exists()
    assert local_config.resolve_local_config(**kwargs).is_file()


def test_ensure_only_writes_workspace_when_installation_is_read_only(
    tmp_path, monkeypatch
):
    package = tmp_path / "install/demo/backend"
    package.mkdir(parents=True)
    original_open = Path.open

    def readonly(path, mode="r", *args, **kwargs):
        if path.is_relative_to(package) and any(flag in mode for flag in "wax+"):
            raise PermissionError("read-only installation")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", readonly)
    monkeypatch.setattr(local_config, "REPOSITORY_ROOT", tmp_path)
    target = local_config.resolve_local_config(
        workspace=tmp_path / "workspace",
        plugin_dir=package,
        plugin_id="demo",
        default_text="value = 4\n",
    )
    assert target.read_text(encoding="utf-8") == "value = 4\n"
    assert list(package.iterdir()) == []
    with pytest.raises(RuntimeError, match="workspace"):
        local_config.resolve_local_config(
            workspace=None, plugin_dir=package, plugin_id="demo", default_text=""
        )


def test_invalid_toml_preserves_original_override(tmp_path, monkeypatch):
    monkeypatch.setattr(local_config, "REPOSITORY_ROOT", tmp_path)
    package = tmp_path / "install/demo"
    package.mkdir(parents=True)
    source = package / "config.local.toml"
    source.write_text("[broken", encoding="utf-8")
    with pytest.raises(ValueError):
        local_config.resolve_local_config(
            workspace=tmp_path / "workspace", plugin_dir=package, plugin_id="demo"
        )
    assert source.read_text(encoding="utf-8") == "[broken"
    assert not (tmp_path / "workspace/plugin-data/demo/config.local.toml").exists()
