from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest

from agent.plugin_packages.contracts import (
    PluginCatalogEntry,
    PluginManifest,
    PluginRelease,
)
from agent.plugin_packages.installer import PluginPackageInstaller


def _manifest(*, version: str = "1.0.0") -> PluginManifest:
    return PluginManifest.from_mapping(
        {
            "schema_version": 1,
            "plugin_id": "desktop-pet",
            "name": "Desktop Pet",
            "description": "Desktop overlay pet",
            "version": version,
            "plugin_api_version": 1,
            "platforms": [{"os": "win32", "arch": "x64"}],
            "entrypoints": {
                "backend": "backend/main.py",
                "desktop": "desktop/index.html",
            },
            "capabilities": ["agent.tool", "desktop.overlay"],
            "permissions": ["plugin.storage"],
            "release": {
                "asset": "desktop-pet.zip",
                "checksums_asset": "checksums.json",
            },
        },
        source="test",
    )


def _archive(manifest: PluginManifest, *, unsafe_name: str | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("plugin.json", json.dumps(manifest.to_dict()))
        archive.writestr("backend/main.py", "print('ready')")
        archive.writestr("desktop/index.html", "<main>pet</main>")
        if unsafe_name is not None:
            archive.writestr(unsafe_name, "escape")
    return output.getvalue()


def _response(url: str, content: bytes, *, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=content,
        request=httpx.Request("GET", url),
    )


class FakeRequester:
    def __init__(self, responses: dict[str, httpx.Response]) -> None:
        self.responses = responses

    async def get(self, url: str, **_: Any) -> httpx.Response:
        return self.responses[url]


def _entry(manifest: PluginManifest) -> PluginCatalogEntry:
    return PluginCatalogEntry(
        repository="Shiori-Plugins/desktop-pet",
        repository_url="https://github.com/Shiori-Plugins/desktop-pet",
        manifest=manifest,
        release=PluginRelease(
            tag=f"v{manifest.version}",
            package_url="https://download/package.zip",
            checksums_url="https://download/checksums.json",
        ),
    )


def _requester(package: bytes, *, digest: str | None = None) -> FakeRequester:
    checksum = digest or hashlib.sha256(package).hexdigest()
    return FakeRequester(
        {
            "https://download/package.zip": _response(
                "https://download/package.zip",
                package,
            ),
            "https://download/checksums.json": _response(
                "https://download/checksums.json",
                json.dumps({"files": {"desktop-pet.zip": checksum}}).encode(),
            ),
        }
    )


async def test_installer_atomically_selects_release_and_preserves_data_on_uninstall(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    package = _archive(manifest)
    installer = PluginPackageInstaller(tmp_path, _requester(package))

    installed = await installer.install(_entry(manifest))
    data_file = tmp_path / "private_runtime" / "plugins" / "desktop-pet" / "state.json"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("{}", encoding="utf-8")

    assert installed.package_dir == (
        tmp_path / "plugins" / "desktop-pet" / "versions" / "1.0.0"
    )
    assert installer.list_installed()[0].version == "1.0.0"
    assert installer.uninstall("desktop-pet") is True
    assert data_file.is_file()


async def test_failed_upgrade_keeps_current_version(tmp_path: Path) -> None:
    first = _manifest(version="1.0.0")
    installer = PluginPackageInstaller(tmp_path, _requester(_archive(first)))
    await installer.install(_entry(first))
    second = _manifest(version="2.0.0")
    broken_installer = PluginPackageInstaller(
        tmp_path,
        _requester(_archive(second), digest="0" * 64),
    )

    with pytest.raises(ValueError, match="checksum mismatch"):
        await broken_installer.install(_entry(second))

    assert installer.list_installed()[0].version == "1.0.0"


async def test_installer_rejects_windows_path_traversal(tmp_path: Path) -> None:
    manifest = _manifest()
    package = _archive(manifest, unsafe_name="..\\outside.txt")
    installer = PluginPackageInstaller(tmp_path, _requester(package))

    with pytest.raises(ValueError, match="unsafe path"):
        await installer.install(_entry(manifest))

    assert not (tmp_path / "outside.txt").exists()


async def test_uninstall_can_explicitly_clear_plugin_data(tmp_path: Path) -> None:
    data_root = tmp_path / "private_runtime" / "plugins" / "desktop-pet"
    data_root.mkdir(parents=True)
    (data_root / "state.json").write_text("{}", encoding="utf-8")
    installer = PluginPackageInstaller(tmp_path, _requester(b"unused"))

    assert installer.uninstall("desktop-pet", purge_data=True) is False
    assert not data_root.exists()


def test_uninstall_rejects_path_like_plugin_id(tmp_path: Path) -> None:
    installer = PluginPackageInstaller(tmp_path, _requester(b"unused"))

    with pytest.raises(ValueError, match="invalid plugin_id"):
        installer.uninstall("..\\outside", purge_data=True)
