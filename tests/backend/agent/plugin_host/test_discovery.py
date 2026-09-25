"""Directory identity, source classification and static admission regressions."""

import pytest

from agent.plugin_host.discovery import discover_plugins


def _discover(roots, external=()):
    return discover_plugins(
        roots, external_roots=list(external), namespace="test", strict=True, host=None
    )


def test_same_basename_different_ids_are_both_visible(contract_package, tmp_path):
    import shutil

    builtin = tmp_path / "host" / contract_package.name
    shutil.copytree(contract_package, builtin)
    path = builtin / "manifest.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("id: external_demo", "id: bundled"),
        encoding="utf-8",
    )
    records = _discover([builtin.parent, tmp_path], [tmp_path])
    assert {record.manifest.id for record in records} == {"bundled", "external_demo"}
    assert len({record.candidate_id for record in records}) == 2
    assert records[0].source == "builtin"
    assert records[0].admission is None
    assert records[1].source == "workspace"
    assert records[1].admission.state == "UNTRUSTED"


@pytest.mark.parametrize("same_root", [False, True])
def test_duplicate_ids_conflict_regardless_of_names_or_source(
    contract_package, tmp_path, same_root
):
    import shutil

    other_root = tmp_path if same_root else tmp_path / "host"
    shutil.copytree(contract_package, other_root / "different-name")
    records = _discover([other_root, tmp_path], [tmp_path])
    assert len(records) == 2
    assert len({record.candidate_id for record in records}) == 2
    for record in records:
        assert record.admission.state == "CONFLICT"
        assert record.admission.code == "duplicate_id"
        assert all(
            str(other.plugin_dir) in record.admission.reason for other in records
        )


@pytest.mark.parametrize(
    "manifest,code",
    [
        ("api: 2\ncapabilities: [", "invalid_manifest"),
        ("- item\n", "invalid_manifest"),
        ("api: 2\nid: legacy\ncapabilities: []\n", "unsupported_contract"),
        ("api: 2\nid: demo\ncapabilities: [unknown]\n", "invalid_manifest"),
    ],
)
def test_external_invalid_manifests_remain_blocked_in_strict_reload(
    tmp_path, manifest, code
):
    package = tmp_path / "bad"
    package.mkdir()
    (package / "manifest.yaml").write_text(manifest, encoding="utf-8")
    records = _discover([tmp_path], [tmp_path])
    assert len(records) == 1
    assert records[0].admission.state == "BLOCKED"
    assert records[0].admission.code == code


@pytest.mark.parametrize(
    "change,code",
    [
        ("entry: ../outside.py", "invalid_path"),
        ("entry: missing.py", "missing_file"),
        ("dependencies: [missing]", "missing_dependency"),
        ("host_dependencies: {python: [not-installed]}", "missing_dependency"),
    ],
)
def test_external_invalid_entries_and_dependencies_are_blocked(
    contract_package, change, code
):
    import yaml

    path = contract_package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(yaml.safe_load(change))
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    record = _discover([contract_package.parent], [contract_package.parent])[0]
    assert record.admission.state == "BLOCKED"
    assert record.admission.code == code


def test_legacy_kv_only_folders_are_ignored_without_mutation(tmp_path):
    folder = tmp_path / "legacy"
    folder.mkdir()
    data = folder / "kv.json"
    data.write_text('{"old":true}', encoding="utf-8")
    assert _discover([tmp_path], [tmp_path]) == []
    assert data.read_text(encoding="utf-8") == '{"old":true}'


def test_workspace_symlink_to_builtin_does_not_grant_trust(
    contract_package, tmp_path, monkeypatch
):
    import os
    import subprocess

    root = tmp_path / "external"
    root.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(contract_package, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"Directory symlinks unavailable: {exc}")
        # Windows junctions exercise the same resolved-directory escape without
        # requiring Developer Mode or elevated symlink privileges.
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(contract_package)],
            check=True,
            capture_output=True,
        )

    def must_not_read(_):
        raise AssertionError("outside-root manifest was read")

    monkeypatch.setattr("agent.plugin_host.discovery.load_manifest", must_not_read)
    records = _discover([root], [root])
    assert records[0].source == "workspace"
    assert records[0].admission.code == "outside_root"
    assert records[0].admission.state == "BLOCKED"


def test_external_manifest_escape_is_checked_before_reading(tmp_path, monkeypatch):
    from pathlib import Path

    root = tmp_path / "plugins"
    package = root / "linked"
    package.mkdir(parents=True)
    manifest = package / "manifest.yaml"
    manifest.write_text("private outside content must not be read", encoding="utf-8")
    outside = tmp_path / "private.yaml"
    outside.write_text("secret", encoding="utf-8")
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        # Model a manifest file symlink on hosts where creating file symlinks
        # requires elevation. Directory junctions are exercised above for real.
        return outside if path == manifest else original_resolve(path, *args, **kwargs)

    def must_not_read(_):
        raise AssertionError("outside-package manifest was read")

    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setattr("agent.plugin_host.discovery.load_manifest", must_not_read)
    record = _discover([root], [root])[0]
    assert record.manifest.id == "linked"
    assert record.admission.state == "BLOCKED"
    assert record.admission.code == "outside_package"
    assert record.admission.field == "manifest"


def test_repeated_identical_roots_do_not_create_a_conflict(contract_package):
    records = _discover([contract_package.parent, contract_package.parent])
    assert len(records) == 1
    assert records[0].admission is None


def _channel_plugin(root, directory, plugin_id, *channels):
    package = root / directory
    (package / "backend").mkdir(parents=True)
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n    pass\n", encoding="utf-8"
    )
    declarations = "".join(
        f"  - {{name: {name}, label: {name},"
        " chat_types: [{type: private, label: 私聊, chat_id_label: ID}]}\n"
        for name in channels
    )
    (package / "manifest.yaml").write_text(
        f"api: 2\nid: {plugin_id}\ncapabilities: [channels]\n"
        + (f"channels:\n{declarations}" if channels else ""),
        encoding="utf-8",
    )


def test_plugins_declaring_one_channel_name_all_conflict(tmp_path):
    _channel_plugin(tmp_path, "first", "first", "shared", "own")
    _channel_plugin(tmp_path, "second", "second", "shared")
    _channel_plugin(tmp_path, "third", "third", "other")
    records = {record.manifest.id: record for record in _discover([tmp_path])}
    for plugin_id in ("first", "second"):
        admission = records[plugin_id].admission
        assert admission is not None
        assert admission.state == "CONFLICT"
        assert admission.code == "duplicate_channel"
        assert admission.field == "channels"
        assert "shared" in admission.reason
        assert "first" in admission.reason and "second" in admission.reason
    assert records["third"].admission is None


def test_duplicate_plugin_id_keeps_its_id_conflict_over_shared_channel(tmp_path):
    _channel_plugin(tmp_path, "copy-a", "same", "shared")
    _channel_plugin(tmp_path, "copy-b", "same", "shared")
    records = _discover([tmp_path])
    assert [record.admission.code for record in records] == [
        "duplicate_id",
        "duplicate_id",
    ]
