"""Pinned official NapCat download and atomic installation."""

from __future__ import annotations

import hashlib
import io
import asyncio
import threading
import zipfile
from unittest.mock import Mock

import pytest

from plugins.qq.backend import napcat_installer
from plugins.qq.backend.napcat_installer import NapCatInstaller


def _archive() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        for name in ("node.exe", "index.js", "wrapper.node", "napcat/napcat.mjs"):
            bundle.writestr(name, "installed")
    return output.getvalue()


@pytest.mark.asyncio
async def test_install_requires_pinned_digest_and_reuses_complete_version(
    monkeypatch, tmp_path
):
    payload = _archive()
    digest = hashlib.sha256(payload).hexdigest()
    manager = NapCatInstaller(tmp_path)
    monkeypatch.setattr(napcat_installer, "managed_available", lambda: True)
    monkeypatch.setattr(napcat_installer, "ARCHIVE_SHA256", digest)
    qq_runtime = tmp_path / "official-qq"
    monkeypatch.setattr(
        napcat_installer, "resolve_official_qq", lambda _directory: qq_runtime
    )
    response = io.BytesIO(payload)
    response.headers = {"Content-Length": str(len(payload))}
    download = Mock(return_value=response)
    monkeypatch.setattr(napcat_installer.urllib.request, "urlopen", download)

    assert await manager.prepare() == qq_runtime
    assert manager.preparation()["stage"] == "ready"
    assert (manager.install_dir / "node.exe").is_file()
    assert await manager.prepare() == qq_runtime
    download.assert_called_once()

    (manager.install_dir / "shiori-install.json").unlink()
    (manager.root / f"{napcat_installer.VERSION}.zip").write_bytes(b"incomplete")
    response = io.BytesIO(payload)
    response.headers = {"Content-Length": str(len(payload))}
    download.return_value = response
    assert await manager.prepare() == qq_runtime
    assert manager.preparation()["stage"] == "ready"
    assert download.call_count == 2


@pytest.mark.asyncio
async def test_incomplete_install_does_not_claim_ready(monkeypatch, tmp_path):
    manager = NapCatInstaller(tmp_path)
    monkeypatch.setattr(napcat_installer, "managed_available", lambda: True)
    monkeypatch.setattr(napcat_installer, "ARCHIVE_SHA256", "0" * 64)
    response = io.BytesIO(_archive())
    response.headers = {"Content-Length": str(len(response.getvalue()))}
    monkeypatch.setattr(
        napcat_installer.urllib.request, "urlopen", lambda *_a, **_k: response
    )
    with pytest.raises(ValueError, match="SHA-256"):
        await manager.prepare()
    assert manager.preparation()["stage"] == "error"
    assert not manager._package_ready()
    assert not manager.install_dir.exists()


@pytest.mark.asyncio
async def test_verified_archive_missing_official_qq_runtime_is_not_ready_and_can_retry(
    monkeypatch, tmp_path
):
    payload = _archive()
    manager = NapCatInstaller(tmp_path)
    monkeypatch.setattr(napcat_installer, "managed_available", lambda: True)
    monkeypatch.setattr(
        napcat_installer, "ARCHIVE_SHA256", hashlib.sha256(payload).hexdigest()
    )
    resolver = Mock(side_effect=RuntimeError("QQ 9.9.31-49738 缺少 crypto.dll"))
    monkeypatch.setattr(napcat_installer, "resolve_official_qq", resolver)
    response = io.BytesIO(payload)
    response.headers = {"Content-Length": str(len(payload))}
    download = Mock(return_value=response)
    monkeypatch.setattr(napcat_installer.urllib.request, "urlopen", download)

    with pytest.raises(RuntimeError, match="缺少 crypto.dll"):
        await manager.prepare()
    assert manager._package_ready()
    assert manager.preparation()["stage"] == "error"
    assert manager.preparation()["percent"] != 100
    assert (manager.root / f"{napcat_installer.VERSION}.zip").is_file()

    resolver.side_effect = None
    resolver.return_value = tmp_path / "official-qq"
    assert await manager.prepare() == tmp_path / "official-qq"
    assert manager.preparation()["stage"] == "ready"
    download.assert_called_once()


@pytest.mark.asyncio
async def test_status_uses_cached_validation_and_prepare_rechecks_off_loop(
    monkeypatch, tmp_path
):
    manager = NapCatInstaller(tmp_path)
    qq_dir = tmp_path / "official-qq"
    gate = threading.Event()

    def validate():
        assert gate.wait(timeout=0.5), "validation blocked the event loop"
        return qq_dir

    validation = Mock(side_effect=validate)
    monkeypatch.setattr(napcat_installer, "managed_available", lambda: True)
    monkeypatch.setattr(manager, "_package_ready", lambda: True)
    monkeypatch.setattr(manager, "_check_native_dependencies", validation)
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, gate.set)
    assert await manager.prepare() == qq_dir
    for _ in range(10):
        assert manager.preparation()["stage"] == "ready"
    validation.assert_called_once()

    gate.clear()
    loop.call_later(0.01, gate.set)
    assert await manager.prepare() == qq_dir
    assert validation.call_count == 2

    validation.side_effect = RuntimeError("QQ 9.9.31-49738 的 crypto.dll 摘要不匹配")
    with pytest.raises(RuntimeError, match="crypto.dll 摘要不匹配"):
        await manager.prepare()
    assert manager.preparation()["stage"] == "error"
    assert "crypto.dll" in manager.preparation()["error"]
