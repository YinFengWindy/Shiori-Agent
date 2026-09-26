"""Pinned official QQ runtime prerequisite for managed NapCat."""

from __future__ import annotations

import hashlib
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from plugins.qq.backend import installed_qq


@pytest.fixture
def fake_registry(monkeypatch):
    registry = ModuleType("winreg")
    setattr(registry, "HKEY_CURRENT_USER", "HKCU")
    setattr(registry, "HKEY_LOCAL_MACHINE", "HKLM")
    entries: dict[tuple[str, str], str] = {}
    attempts: list[tuple[str, str]] = []

    class Key:
        def __init__(self, value: str) -> None:
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def open_key(hive: str, name: str):
        attempts.append((hive, name))
        return Key(entries[(hive, name)]) if (hive, name) in entries else _missing()

    def _missing():
        raise FileNotFoundError("registry key absent")

    def query_value(key: Key, name: str):
        assert name == "UninstallString"
        return key.value, 1

    setattr(registry, "OpenKey", open_key)
    setattr(registry, "QueryValueEx", query_value)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(installed_qq, "os", SimpleNamespace(name="nt"))
    return entries, attempts


def _qq_root(tmp_path, name: str):
    root = tmp_path / name
    root.mkdir()
    (root / "Uninstall.exe").write_bytes(b"official uninstaller")
    (root / "QQ.exe").write_bytes(b"official QQ")
    return root


def test_registry_prefers_valid_current_user_install(fake_registry, tmp_path):
    entries, attempts = fake_registry
    current = _qq_root(tmp_path, "Current User QQ")
    machine = _qq_root(tmp_path, "Machine QQ")
    key = installed_qq._UNINSTALL_KEYS[0]
    entries[("HKCU", key)] = f'"{current / "Uninstall.exe"}"'
    entries[("HKLM", key)] = str(machine / "Uninstall.exe")

    assert installed_qq._install_root() == current
    assert attempts == [("HKCU", key)]


def test_registry_skips_invalid_entries_then_uses_machine_install(
    fake_registry, tmp_path
):
    entries, attempts = fake_registry
    invalid = tmp_path / "Missing QQ.exe"
    invalid.mkdir()
    (invalid / "Uninstall.exe").write_bytes(b"uninstaller only")
    machine = _qq_root(tmp_path, "Machine QQ")
    first, second = installed_qq._UNINSTALL_KEYS
    entries[("HKCU", first)] = "cmd /c uninstall"
    entries[("HKCU", second)] = str(invalid / "Uninstall.exe")
    entries[("HKLM", first)] = str(machine / "Uninstall.exe")

    assert installed_qq._install_root() == machine
    assert attempts == [("HKCU", first), ("HKCU", second), ("HKLM", first)]


def test_registry_missing_install_reports_required_qq_version(fake_registry):
    _entries, attempts = fake_registry
    with pytest.raises(RuntimeError, match="官方 QQ 9.9.31-49738"):
        installed_qq._install_root()
    assert attempts == [
        (hive, name)
        for hive in ("HKCU", "HKLM")
        for name in installed_qq._UNINSTALL_KEYS
    ]


def test_pinned_native_hashes_are_complete():
    assert {
        name: len(digest) for name, digest in installed_qq._EXPECTED_SHA256.items()
    } == {
        "crypto.dll": 64,
        "ssl.dll": 64,
        "wrapper.node": 64,
    }


@pytest.fixture
def qq_install(monkeypatch, tmp_path):
    root = tmp_path / "Tencent QQ"
    config = root / "versions" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps({"curVersion": installed_qq.QQ_VERSION}), encoding="utf-8"
    )
    app_dir = root / "versions" / installed_qq.QQ_VERSION / "resources" / "app"
    app_dir.mkdir(parents=True)
    napcat_dir = tmp_path / "official-napcat"
    napcat_dir.mkdir()
    contents = {
        "crypto.dll": b"signed Tencent crypto",
        "ssl.dll": b"signed Tencent ssl",
        "wrapper.node": b"version-matched wrapper",
    }
    for name, data in contents.items():
        (app_dir / name).write_bytes(data)
    (napcat_dir / "wrapper.node").write_bytes(contents["wrapper.node"])
    monkeypatch.setattr(installed_qq, "_install_root", lambda: root)
    monkeypatch.setattr(
        installed_qq,
        "_EXPECTED_SHA256",
        {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    )
    return root, app_dir, napcat_dir


def test_matching_official_qq_runtime_is_accepted(qq_install):
    _root, app_dir, napcat_dir = qq_install
    assert installed_qq.resolve_official_qq(napcat_dir) == app_dir


def test_wrong_qq_version_is_rejected(qq_install):
    root, _app_dir, napcat_dir = qq_install
    (root / "versions" / "config.json").write_text(
        '{"curVersion":"9.9.30-older"}', encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="需要 QQ 9.9.31-49738"):
        installed_qq.resolve_official_qq(napcat_dir)


@pytest.mark.parametrize("name", ["crypto.dll", "ssl.dll", "wrapper.node"])
def test_missing_native_file_is_rejected(qq_install, name):
    _root, app_dir, napcat_dir = qq_install
    (app_dir / name).unlink()
    with pytest.raises(RuntimeError, match=f"缺少 {name}"):
        installed_qq.resolve_official_qq(napcat_dir)


@pytest.mark.parametrize("name", ["crypto.dll", "ssl.dll", "wrapper.node"])
def test_modified_native_file_is_rejected(qq_install, name):
    _root, app_dir, napcat_dir = qq_install
    (app_dir / name).write_bytes(b"modified")
    with pytest.raises(RuntimeError, match=f"{name} 摘要不匹配"):
        installed_qq.resolve_official_qq(napcat_dir)


def test_modified_bundled_wrapper_is_rejected_before_using_qq(qq_install):
    _root, _app_dir, napcat_dir = qq_install
    (napcat_dir / "wrapper.node").write_bytes(b"modified")
    with pytest.raises(RuntimeError, match="NapCat 官方组件 wrapper.node"):
        installed_qq.resolve_official_qq(napcat_dir)
