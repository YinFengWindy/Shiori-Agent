"""Pinned official QQ runtime prerequisite for managed NapCat."""

from __future__ import annotations

import hashlib
import json

import pytest

from plugins.qq.backend import installed_qq


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
