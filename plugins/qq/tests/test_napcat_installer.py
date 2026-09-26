"""Pinned official NapCat download and atomic installation."""

from __future__ import annotations

import hashlib
import io
import zipfile
from unittest.mock import Mock

import pytest

from plugins.qq.backend import napcat_installer
from plugins.qq.backend.napcat_installer import NapCatInstaller


def _archive() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        for name in ("node.exe", "index.js", "napcat/napcat.mjs"):
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
    response = io.BytesIO(payload)
    response.headers = {"Content-Length": str(len(payload))}
    download = Mock(return_value=response)
    monkeypatch.setattr(napcat_installer.urllib.request, "urlopen", download)

    await manager.prepare()
    assert manager.preparation()["stage"] == "ready"
    assert (manager.install_dir / "node.exe").is_file()
    await manager.prepare()
    download.assert_called_once()

    (manager.install_dir / "shiori-install.json").unlink()
    (manager.root / f"{napcat_installer.VERSION}.zip").write_bytes(b"incomplete")
    response = io.BytesIO(payload)
    response.headers = {"Content-Length": str(len(payload))}
    download.return_value = response
    await manager.prepare()
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
    assert not manager._ready()
    assert not manager.install_dir.exists()
