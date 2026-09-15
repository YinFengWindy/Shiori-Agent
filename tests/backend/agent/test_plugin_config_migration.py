"""Legacy settings upgrade preserves authoritative edits and all failed sources."""

import json
from pathlib import Path
import shutil
import tomllib

import pytest

import agent.plugin_config_migration as migration
from agent.config import load_config, load_config_text
from infra.persistence.toml_store import render_toml


def _environment(tmp_path, monkeypatch, text=""):
    workspace = tmp_path / "workspace"
    packages = tmp_path / "checkout/plugins"
    (packages / "demo").mkdir(parents=True)
    (packages / "demo/manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
    )
    monkeypatch.setattr(migration, "plugin_roots", lambda: [packages])
    monkeypatch.setattr(migration, "REPOSITORY_ROOT", packages.parent)
    path = tmp_path / "separate-config/config.toml"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    sources = [
        workspace / "plugin-data/demo/plugin_config.json",
        workspace / "plugins/demo/plugin_config.json",
        packages / "demo/plugin_config.json",
        packages / "demo/backend/plugin_config.json",
        packages.parent / "apps/backend/plugins/demo/plugin_config.json",
        packages.parent / "apps/backend/plugins/demo/backend/plugin_config.json",
    ]
    return path, workspace, packages, sources


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.mark.parametrize("source_index", range(6))
def test_each_legacy_location_is_live_after_upgrade_and_code_replacement(
    tmp_path, monkeypatch, source_index
):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    value = {"secret": "keep", "nested": {"ports": [1, 2]}}
    _write(sources[source_index], value)
    assert load_config(path, workspace=workspace).plugins["demo"] == value
    assert json.loads(sources[0].read_text(encoding="utf-8")) == value
    if source_index:
        assert not sources[source_index].exists()
    if packages.exists():
        shutil.rmtree(packages)
    _write(packages / "demo/plugin_config.json", {"secret": "replacement"})
    before = path.read_bytes()
    assert load_config(path, workspace=workspace).plugins["demo"] == value
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "indices, expected", [([1, 2, 4], 1), ([0, 1, 2], 0), ([2, 4], 2)]
)
def test_priority_and_only_selected_source_is_removed(
    tmp_path, monkeypatch, indices, expected
):
    path, workspace, _, sources = _environment(tmp_path, monkeypatch)
    for index in indices:
        _write(sources[index], {"value": index})
    assert load_config(path, workspace=workspace).plugins["demo"] == {"value": expected}
    for index in indices:
        assert sources[index].exists() is (index == 0 or index != expected)


@pytest.mark.parametrize("existing", [{}, {"value": "current"}, {"enabled": False}])
def test_authoritative_tables_win_but_old_toggle_only_tables_keep_legacy_settings(
    tmp_path, monkeypatch, existing
):
    path, workspace, _, sources = _environment(
        tmp_path, monkeypatch, render_toml({"plugins": {"demo": existing}})
    )
    _write(sources[1], {"value": "legacy", "enabled": True})
    expected = (
        {"value": "legacy", "enabled": False}
        if existing == {"enabled": False}
        else existing
    )
    assert load_config(path, workspace=workspace).plugins["demo"] == expected


@pytest.mark.parametrize("stage", ["archive", "config", "marker"])
def test_failed_upgrade_preserves_sources_and_retries_without_reimporting(
    tmp_path, monkeypatch, stage
):
    path, workspace, _, sources = _environment(tmp_path, monkeypatch)
    _write(sources[1], {"value": "original"})
    original = sources[1].read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        if stage == "archive":
            patch.setattr("agent.plugin_host.plugin_data.atomic_save_json", fail)
        elif stage == "config":
            patch.setattr(migration, "atomic_save_text", fail)
        else:
            patch.setattr(migration, "atomic_save_json", fail)
        with pytest.raises(OSError, match="disk full"):
            load_config(path, workspace=workspace)
    assert sources[1].read_bytes() == original
    if stage == "archive":
        assert not sources[0].exists()
    if stage != "marker":
        assert path.read_bytes() == b""
    else:
        # Simulate a crash after the TOML commit: that receipt must prevent
        # reimport even if the archive changes before recovery finishes.
        _write(sources[0], {"value": "stale"})
    assert load_config(path, workspace=workspace).plugins["demo"] == {
        "value": "original"
    }


def test_settings_form_save_then_raw_removal_cannot_revive_legacy_json(
    tmp_path, monkeypatch
):
    from desktop_bridge.runtime.settings_form import settings_form_write

    path, workspace, _, sources = _environment(tmp_path, monkeypatch)
    _write(sources[1], {"secret": "legacy"})
    load_config(path, workspace=workspace)
    derive = settings_form_write(
        {"config_toml": "max_tokens = 100\n", "preserve_plugins": True}
    )
    assert derive is not None
    ordinary = derive.build_config_toml(path.read_text(encoding="utf-8"))
    assert "_migrations" not in tomllib.loads(ordinary)
    path.write_text(ordinary, encoding="utf-8")
    assert load_config(path, workspace=workspace).plugins["demo"]["secret"] == "legacy"
    # Raw apply owns the entire document, including intentional table removal.
    path.write_text("max_tokens = 200\n", encoding="utf-8")
    assert load_config(path, workspace=workspace).plugins == {}
    assert path.read_text(encoding="utf-8") == "max_tokens = 200\n"
    assert sources[0].is_file()


def test_read_only_source_can_be_archived_and_never_overrides_later_edits(
    tmp_path, monkeypatch
):
    path, workspace, _, sources = _environment(tmp_path, monkeypatch)
    _write(sources[2], {"value": "old"})
    unlink = Path.unlink

    def readonly(file, *args, **kwargs):
        if file == sources[2]:
            raise PermissionError("read-only install")
        return unlink(file, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", readonly)
    assert load_config(path, workspace=workspace).plugins["demo"] == {"value": "old"}
    assert sources[2].is_file()
    path.write_text("[plugins.demo]\n", encoding="utf-8")
    assert load_config(path, workspace=workspace).plugins["demo"] == {}


@pytest.mark.parametrize("value", [[1], {"unsupported": None}])
def test_invalid_legacy_values_do_not_touch_sources_or_config(
    tmp_path, monkeypatch, value
):
    path, workspace, _, sources = _environment(tmp_path, monkeypatch)
    _write(sources[1], value)
    with pytest.raises((ValueError, TypeError)):
        load_config(path, workspace=workspace)
    assert sources[1].is_file()
    assert not sources[0].exists()
    assert path.read_bytes() == b""


def test_candidate_parsing_and_loading_without_workspace_do_not_migrate(
    tmp_path, monkeypatch
):
    path, _, _, sources = _environment(tmp_path, monkeypatch)
    _write(sources[1], {"value": "old"})
    assert load_config_text("").plugins == {}
    assert load_config(path).plugins == {}
    assert sources[1].is_file()
    assert not sources[0].exists()


@pytest.mark.parametrize("location", ["workspace", "package", "old"])
def test_directory_name_resolves_to_manifest_identity(tmp_path, monkeypatch, location):
    path, workspace, packages, _ = _environment(tmp_path, monkeypatch)
    (packages / "demo/manifest.yaml").write_text(
        "api: 2\nid: stable-id\ncapabilities: []\n", encoding="utf-8"
    )
    root = {
        "workspace": workspace / "plugins",
        "package": packages,
        "old": packages.parent / "apps/backend/plugins",
    }[location]
    source = root / "demo/plugin_config.json"
    _write(source, {"value": "kept"})
    assert load_config(path, workspace=workspace).plugins == {
        "stable-id": {"value": "kept"}
    }
    assert (workspace / "plugin-data/stable-id/plugin_config.json").is_file()
    assert not source.exists()
    assert not (workspace / "plugin-data/demo").exists()


def test_unknown_or_ambiguous_owner_leaves_legacy_data_untouched(tmp_path, monkeypatch):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    (packages / "demo/manifest.yaml").unlink()
    _write(sources[1], {"value": "kept"})
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[1].is_file()
    assert not sources[0].exists()
    for directory in ("demo", "duplicate"):
        package = packages / directory
        package.mkdir(exist_ok=True)
        (package / "manifest.yaml").write_text(
            "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
        )
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[1].is_file()
    assert not sources[0].exists()


def test_untrusted_path_identity_is_not_used_to_migrate_files(tmp_path, monkeypatch):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    (packages / "demo/manifest.yaml").write_text(
        "api: 2\nid: ../outside\ncapabilities: []\n", encoding="utf-8"
    )
    _write(sources[2], {"value": "kept"})
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[2].is_file()
    assert not (workspace / "plugin-data").exists()


def test_overlapping_workspace_and_package_roots_are_one_owner(tmp_path, monkeypatch):
    path, _, packages, sources = _environment(tmp_path, monkeypatch)
    _write(sources[2], {"value": "kept"})
    assert load_config(path, workspace=packages.parent).plugins == {
        "demo": {"value": "kept"}
    }
    assert not sources[2].exists()
