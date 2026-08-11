from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Protocol

import httpx

from agent.plugin_packages.contracts import PluginCatalogEntry, PluginManifest
from infra.persistence.json_store import atomic_save_json, load_json

_MAX_PACKAGE_BYTES = 128 * 1024 * 1024
_MAX_EXPANDED_BYTES = 512 * 1024 * 1024
_PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class HttpGetter(Protocol):
    """Minimal asynchronous HTTP contract required to download release assets."""

    async def get(self, url: str, **kwargs: Any) -> httpx.Response: ...


@dataclass(frozen=True)
class InstalledPlugin:
    """One atomically selected installed plugin version."""

    plugin_id: str
    version: str
    package_dir: Path
    manifest: PluginManifest

    def to_dict(self) -> dict[str, object]:
        """Serializes installed plugin metadata for bridge responses."""

        return {
            "plugin_id": self.plugin_id,
            "version": self.version,
            "package_dir": str(self.package_dir),
            "manifest": self.manifest.to_dict(),
        }


class PluginPackageInstaller:
    """Downloads, validates and atomically selects plugin release packages."""

    def __init__(self, workspace: Path, requester: HttpGetter) -> None:
        self._requester = requester
        self._packages_root = workspace / "plugins"
        self._data_root = workspace / "private_runtime" / "plugins"

    async def install(self, entry: PluginCatalogEntry) -> InstalledPlugin:
        """Installs or upgrades one catalog entry without executing plugin code."""

        if not entry.installable or entry.release is None:
            raise ValueError(
                entry.unavailable_reason or "plugin release is unavailable"
            )
        package_response = await self._requester.get(
            entry.release.package_url,
            follow_redirects=True,
        )
        package_response.raise_for_status()
        package_bytes = package_response.content
        if not package_bytes or len(package_bytes) > _MAX_PACKAGE_BYTES:
            raise ValueError("plugin package size is invalid")
        checksums_response = await self._requester.get(
            entry.release.checksums_url,
            follow_redirects=True,
        )
        checksums_response.raise_for_status()
        expected_digest = _checksum_for_asset(
            checksums_response.content,
            entry.manifest.release.asset,
        )
        actual_digest = hashlib.sha256(package_bytes).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError("plugin package checksum mismatch")
        return self._install_archive(package_bytes, expected=entry.manifest)

    def list_installed(self) -> list[InstalledPlugin]:
        """Returns every valid atomically selected installed plugin."""

        if not self._packages_root.is_dir():
            return []
        installed: list[InstalledPlugin] = []
        for plugin_root in sorted(self._packages_root.iterdir()):
            if not plugin_root.is_dir():
                continue
            current = load_json(
                plugin_root / "current.json",
                default=None,
                domain="plugin_packages",
            )
            if not isinstance(current, Mapping):
                continue
            version = str(current.get("version") or "").strip()
            package_dir = plugin_root / "versions" / version
            manifest_path = package_dir / "plugin.json"
            if not version or not manifest_path.is_file():
                continue
            manifest = PluginManifest.from_json_bytes(
                manifest_path.read_bytes(),
                source=str(manifest_path),
            )
            if manifest.plugin_id != plugin_root.name or manifest.version != version:
                raise ValueError(
                    f"installed plugin registry mismatch: {plugin_root.name}"
                )
            installed.append(
                InstalledPlugin(
                    plugin_id=manifest.plugin_id,
                    version=version,
                    package_dir=package_dir,
                    manifest=manifest,
                )
            )
        return installed

    def uninstall(self, plugin_id: str, *, purge_data: bool = False) -> bool:
        """Removes installed code and optionally deletes plugin-owned user data."""

        plugin_root = self._plugin_root(plugin_id)
        existed = plugin_root.exists()
        if existed:
            shutil.rmtree(plugin_root)
        if purge_data:
            data_root = self._data_root / plugin_id
            if data_root.exists():
                shutil.rmtree(data_root)
        return existed

    def _install_archive(
        self,
        package_bytes: bytes,
        *,
        expected: PluginManifest,
    ) -> InstalledPlugin:
        plugin_root = self._plugin_root(expected.plugin_id)
        versions_root = plugin_root / "versions"
        versions_root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".install-", dir=plugin_root))
        try:
            archive_path = temporary / "package.zip"
            archive_path.write_bytes(package_bytes)
            extracted = temporary / "extracted"
            extracted.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                _validate_archive(archive)
                archive.extractall(extracted)
            package_root = _single_package_root(extracted)
            manifest_path = package_root / "plugin.json"
            if not manifest_path.is_file():
                raise ValueError("plugin package is missing plugin.json")
            manifest = PluginManifest.from_json_bytes(
                manifest_path.read_bytes(),
                source="release:plugin.json",
            )
            if manifest != expected:
                raise ValueError(
                    "release plugin manifest does not match repository manifest"
                )
            _validate_entrypoints(package_root, manifest)
            destination = versions_root / manifest.version
            if not destination.exists():
                os.replace(package_root, destination)
            atomic_save_json(
                plugin_root / "current.json",
                {"version": manifest.version},
                domain="plugin_packages",
            )
            return InstalledPlugin(
                plugin_id=manifest.plugin_id,
                version=manifest.version,
                package_dir=destination,
                manifest=manifest,
            )
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def _plugin_root(self, plugin_id: str) -> Path:
        if not _PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise ValueError("invalid plugin_id")
        return self._packages_root / plugin_id


def _checksum_for_asset(raw: bytes, asset_name: str) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("plugin checksums asset is invalid JSON") from exc
    files = payload.get("files") if isinstance(payload, Mapping) else None
    if not isinstance(files, Mapping):
        raise ValueError("plugin checksums asset must contain a files object")
    digest = files.get(asset_name)
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("plugin package checksum is missing")
    clean_digest = digest.lower()
    if any(character not in "0123456789abcdef" for character in clean_digest):
        raise ValueError("plugin package checksum is invalid")
    return clean_digest


def _validate_archive(archive: zipfile.ZipFile) -> None:
    expanded_size = 0
    names: set[str] = set()
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        if (
            not entry.filename
            or "\\" in entry.filename
            or path.is_absolute()
            or ".." in path.parts
            or path == "."
            or (path.parts and path.parts[0].endswith(":"))
        ):
            raise ValueError("plugin package contains an unsafe path")
        normalized = path.as_posix()
        if normalized in names:
            raise ValueError("plugin package contains duplicate paths")
        names.add(normalized)
        expanded_size += entry.file_size
        if expanded_size > _MAX_EXPANDED_BYTES:
            raise ValueError("plugin package expanded size is too large")
        mode = entry.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError("plugin package cannot contain symbolic links")


def _single_package_root(extracted: Path) -> Path:
    if (extracted / "plugin.json").is_file():
        return extracted
    children = [item for item in extracted.iterdir() if item.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    raise ValueError("plugin package must contain one root with plugin.json")


def _validate_entrypoints(package_root: Path, manifest: PluginManifest) -> None:
    for entrypoint in (manifest.entrypoints.backend, manifest.entrypoints.desktop):
        if entrypoint is None:
            continue
        target = (package_root / entrypoint).resolve()
        try:
            target.relative_to(package_root.resolve())
        except ValueError as exc:
            raise ValueError("plugin entrypoint escapes package root") from exc
        if not target.is_file():
            raise ValueError(f"plugin package entrypoint is missing: {entrypoint}")
