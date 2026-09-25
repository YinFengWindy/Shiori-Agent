"""Legacy settings upgrade preserves authoritative edits and all failed sources."""

import json
from pathlib import Path
import shutil
import tomllib

import pytest

import agent.plugin_config_migration as migration
from agent.config import load_config, load_config_text
from infra.persistence.toml_store import render_toml


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
    # The form save keeps host-owned receipts; only a raw full-document write
    # (below) can drop them, which the workspace marker must survive.
    assert tomllib.loads(ordinary)["_migrations"]["plugin_config_json"] == ["demo"]
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


def test_repeated_builtin_root_does_not_create_a_migration_conflict(
    tmp_path, monkeypatch
):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    monkeypatch.setattr(migration, "plugin_roots", lambda: [packages, packages])
    _write(sources[2], {"value": "kept"})
    assert load_config(path, workspace=workspace).plugins == {"demo": {"value": "kept"}}
    assert not sources[2].exists()


@pytest.mark.parametrize("duplicate_location", ["later-root", "old-workspace"])
def test_same_id_conflict_never_imports_or_deletes_either_source(
    tmp_path, monkeypatch, duplicate_location
):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    duplicate_root = (
        tmp_path / "later-packages"
        if duplicate_location == "later-root"
        else workspace / "plugins"
    )
    duplicate = duplicate_root / "demo"
    duplicate.mkdir(parents=True)
    (duplicate / "manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
    )
    if duplicate_location == "later-root":
        monkeypatch.setattr(
            migration, "plugin_roots", lambda: [packages, duplicate_root]
        )
    _write(sources[2], {"value": "installed"})
    other_source = duplicate / "plugin_config.json"
    _write(other_source, {"value": "other"})
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[2].is_file()
    assert other_source.is_file()
    assert not sources[0].exists()
    assert path.read_bytes() == b""


def test_workspace_only_package_is_not_an_installed_migration_owner(
    tmp_path, monkeypatch
):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    (packages / "demo/manifest.yaml").unlink()
    _write(sources[1], {"value": "legacy"})
    (sources[1].parent / "manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
    )
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[1].is_file()
    assert not sources[0].exists()


@pytest.mark.parametrize("external", [False, True])
def test_same_directory_different_ids_never_share_package_json(
    tmp_path, monkeypatch, external
):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    other_root = workspace / "plugins" if external else tmp_path / "other-builtin"
    other = other_root / "demo"
    other.mkdir(parents=True)
    (other / "manifest.yaml").write_text(
        "api: 2\nid: other\ncapabilities: []\n", encoding="utf-8"
    )
    if not external:
        monkeypatch.setattr(migration, "plugin_roots", lambda: [packages, other_root])
    _write(sources[2], {"value": "builtin"})
    other_source = other / "plugin_config.json"
    _write(other_source, {"value": "other"})
    expected = {"demo": {"value": "builtin"}}
    if not external:
        expected["other"] = {"value": "other"}
    assert load_config(path, workspace=workspace).plugins == expected
    assert other_source.exists() is external
    assert not sources[2].exists()
    if external:
        assert not (workspace / "plugin-data/other").exists()


@pytest.mark.parametrize("admission", ["UNTRUSTED", "BLOCKED", "CONFLICT"])
def test_discovery_admission_defers_import_but_finishes_committed_receipt(
    tmp_path, monkeypatch, admission
):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    external = workspace / "plugins/demo"
    (packages / "demo/manifest.yaml").unlink()
    (external / "backend").mkdir(parents=True)
    (external / "backend/plugin.py").write_text(
        "raise AssertionError('must not execute')\nasync def setup(ctx):\n    pass\n",
        encoding="utf-8",
    )
    (external / "manifest.yaml").write_text(
        "api: 2\npackage_contract: 1\nid: demo\nversion: 1.0.0\n"
        "runtime_api: '>=2.0.0 <3.0.0'\nentry: backend/plugin.py\ncapabilities: []\n",
        encoding="utf-8",
    )
    if admission == "BLOCKED":
        (external / "backend/plugin.py").unlink()
    if admission == "CONFLICT":
        (packages / "demo/manifest.yaml").write_text(
            "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
        )
    from agent.plugin_host.discovery import discover_plugins

    records = discover_plugins(
        [packages, external.parent],
        external_roots=[external.parent],
        namespace="test",
        strict=False,
        host=None,
    )
    assert records[-1].admission.state == admission
    _write(sources[1], {"value": "source"})
    _write(sources[0], {"value": "archive"})
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[1].is_file()
    assert path.read_bytes() == b""
    # A crash receipt may exist from an earlier admitted installation. Changed
    # admission only blocks importing settings and deleting legacy sources.
    path.write_text(
        '[plugins.demo]\nvalue = "committed"\n[_migrations]\nplugin_config_json = ["demo"]\n',
        encoding="utf-8",
    )
    before = path.read_bytes()
    sources[0].write_text(
        "invalid archive must not be read during recovery", encoding="utf-8"
    )
    assert load_config(path, workspace=workspace).plugins["demo"] == {
        "value": "committed"
    }
    assert path.read_bytes() == before
    assert sources[1].is_file()
    assert (workspace / "plugin-data/demo/plugin_config.migrated.json").is_file()


def test_ambiguous_manifest_free_directory_alias_is_preserved(tmp_path, monkeypatch):
    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    (packages / "demo/manifest.yaml").write_text(
        "api: 2\nid: first\ncapabilities: []\n", encoding="utf-8"
    )
    other = tmp_path / "other-builtin/demo"
    other.mkdir(parents=True)
    (other / "manifest.yaml").write_text(
        "api: 2\nid: second\ncapabilities: []\n", encoding="utf-8"
    )
    monkeypatch.setattr(migration, "plugin_roots", lambda: [packages, other.parent])
    _write(sources[1], {"value": "ambiguous"})
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[1].is_file()
    assert not (workspace / "plugin-data").exists()


@pytest.mark.parametrize(
    "location, expected_id",
    [("workspace", "beta"), ("old-root", "gamma"), ("old-backend", "gamma")],
)
def test_canonical_id_and_package_alias_have_separate_legacy_namespaces(
    tmp_path, monkeypatch, location, expected_id
):
    path, workspace, packages, _ = _environment(tmp_path, monkeypatch)
    (packages / "demo/manifest.yaml").unlink()
    for directory, plugin_id in (("alpha", "beta"), ("beta", "gamma")):
        package = packages / directory
        package.mkdir()
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {plugin_id}\ncapabilities: []\n", encoding="utf-8"
        )
    root = (
        workspace / "plugins"
        if location == "workspace"
        else packages.parent / "apps/backend/plugins"
    )
    source = (
        root
        / "beta"
        / (
            "backend/plugin_config.json"
            if location == "old-backend"
            else "plugin_config.json"
        )
    )
    _write(source, {"secret": "one-owner"})
    assert load_config(path, workspace=workspace).plugins == {
        expected_id: {"secret": "one-owner"}
    }
    other_id = "gamma" if expected_id == "beta" else "beta"
    assert not (workspace / "plugin-data" / other_id).exists()
    assert not source.exists()


def test_committed_receipt_survives_conflict_settings_save_and_table_deletion(
    tmp_path, monkeypatch
):
    from desktop_bridge.runtime.settings_form import settings_form_write

    path, workspace, packages, sources = _environment(tmp_path, monkeypatch)
    _write(sources[2], {"secret": "old"})
    original = sources[2].read_bytes()

    def fail_marker(*args, **kwargs):
        raise OSError("marker failed")

    with monkeypatch.context() as patch:
        patch.setattr(migration, "atomic_save_json", fail_marker)
        with pytest.raises(OSError, match="marker failed"):
            load_config(path, workspace=workspace)
    assert tomllib.loads(path.read_text(encoding="utf-8"))["plugins"]["demo"] == {
        "secret": "old"
    }
    conflicting = workspace / "plugins/demo/manifest.yaml"
    conflicting.parent.mkdir(parents=True)
    conflicting.write_text("api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8")
    unlink = Path.unlink

    def readonly(file, *args, **kwargs):
        if file == sources[2]:
            raise AssertionError(
                "receipt recovery must not delete the read-only source"
            )
        return unlink(file, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", readonly)
    load_config(path, workspace=workspace)
    derive = settings_form_write(
        {"config_toml": "max_tokens = 100\n", "preserve_plugins": True}
    )
    assert derive is not None
    path.write_text(
        derive.build_config_toml(path.read_text(encoding="utf-8")), encoding="utf-8"
    )
    receipts = tomllib.loads(path.read_text(encoding="utf-8"))["_migrations"]
    assert receipts["plugin_config_json"] == ["demo"]
    # A subsequent raw settings edit intentionally removes the entire table.
    path.write_text("max_tokens = 200\n", encoding="utf-8")
    conflicting.unlink()
    assert load_config(path, workspace=workspace).plugins == {}
    assert sources[2].read_bytes() == original
    assert (workspace / "plugin-data/demo/plugin_config.migrated.json").is_file()
