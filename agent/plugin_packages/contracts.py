from __future__ import annotations

import json
import platform
import re
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

PLUGIN_REPOSITORY_MANIFEST_PATH = ".akashic-plugin/plugin.json"
HOST_PLUGIN_API_VERSION = 1
_PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")


class PluginManifestError(ValueError):
    """Raised when a repository or packaged plugin manifest is invalid."""


@dataclass(frozen=True)
class PluginPlatform:
    """One operating-system and CPU pair supported by a plugin release."""

    os: str
    arch: str


@dataclass(frozen=True)
class PluginEntrypoints:
    """Runtime entrypoints contained inside the installed plugin package."""

    backend: str | None
    desktop: str | None


@dataclass(frozen=True)
class PluginReleaseContract:
    """Release asset names used to install one plugin version."""

    asset: str
    checksums_asset: str


@dataclass(frozen=True)
class PluginManifest:
    """Validated public contract shared by repository and release manifests."""

    schema_version: int
    plugin_id: str
    name: str
    description: str
    version: str
    plugin_api_version: int
    platforms: tuple[PluginPlatform, ...]
    entrypoints: PluginEntrypoints
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    release: PluginReleaseContract

    @classmethod
    def from_json_bytes(cls, raw: bytes, *, source: str) -> "PluginManifest":
        """Decodes and validates a UTF-8 plugin manifest."""

        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginManifestError(
                f"plugin manifest is not valid UTF-8 JSON: {source}"
            ) from exc
        if not isinstance(value, Mapping):
            raise PluginManifestError(f"plugin manifest must be an object: {source}")
        return cls.from_mapping(value, source=source)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        source: str,
    ) -> "PluginManifest":
        """Validates a decoded plugin manifest mapping."""

        schema_version = _required_int(value, "schema_version", source=source)
        if schema_version != 1:
            raise PluginManifestError(
                f"unsupported plugin manifest schema_version {schema_version}: {source}"
            )
        plugin_id = _required_string(value, "plugin_id", source=source)
        if not _PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise PluginManifestError(f"invalid plugin_id {plugin_id!r}: {source}")
        version = _required_string(value, "version", source=source)
        if not _VERSION_PATTERN.fullmatch(version):
            raise PluginManifestError(f"invalid semantic version {version!r}: {source}")
        plugin_api_version = _required_int(
            value,
            "plugin_api_version",
            source=source,
        )
        raw_platforms = value.get("platforms")
        if not isinstance(raw_platforms, list) or not raw_platforms:
            raise PluginManifestError(f"platforms must be a non-empty array: {source}")
        platforms = tuple(
            _parse_platform(item, source=source) for item in raw_platforms
        )
        entrypoints = _parse_entrypoints(value.get("entrypoints"), source=source)
        capabilities = _string_tuple(
            value.get("capabilities", []),
            field="capabilities",
            source=source,
            pattern=_CAPABILITY_PATTERN,
        )
        permissions = _string_tuple(
            value.get("permissions", []),
            field="permissions",
            source=source,
            pattern=_CAPABILITY_PATTERN,
        )
        release = _parse_release(value.get("release"), source=source)
        return cls(
            schema_version=schema_version,
            plugin_id=plugin_id,
            name=_required_string(value, "name", source=source),
            description=str(value.get("description") or "").strip(),
            version=version,
            plugin_api_version=plugin_api_version,
            platforms=platforms,
            entrypoints=entrypoints,
            capabilities=capabilities,
            permissions=permissions,
            release=release,
        )

    def supports_host(self, *, os_name: str, arch: str, api_version: int) -> bool:
        """Returns whether this manifest supports one concrete Shiori host."""

        return self.plugin_api_version == api_version and any(
            item.os == os_name and item.arch == arch for item in self.platforms
        )

    def to_dict(self) -> dict[str, object]:
        """Serializes the validated manifest for installed registry records."""

        return {
            "schema_version": self.schema_version,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "plugin_api_version": self.plugin_api_version,
            "platforms": [
                {"os": item.os, "arch": item.arch} for item in self.platforms
            ],
            "entrypoints": {
                **(
                    {"backend": self.entrypoints.backend}
                    if self.entrypoints.backend
                    else {}
                ),
                **(
                    {"desktop": self.entrypoints.desktop}
                    if self.entrypoints.desktop
                    else {}
                ),
            },
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "release": {
                "asset": self.release.asset,
                "checksums_asset": self.release.checksums_asset,
            },
        }


@dataclass(frozen=True)
class PluginRelease:
    """Resolved GitHub Release assets for one installable plugin version."""

    tag: str
    package_url: str
    checksums_url: str


@dataclass(frozen=True)
class PluginCatalogEntry:
    """One repository plugin and its latest compatible release, when available."""

    repository: str
    repository_url: str
    manifest: PluginManifest
    release: PluginRelease | None
    unavailable_reason: str | None = None

    @property
    def installable(self) -> bool:
        """Returns whether this catalog entry can be installed now."""

        return self.release is not None and self.unavailable_reason is None


def current_host_platform() -> tuple[str, str]:
    """Returns normalized platform identifiers used by plugin manifests."""

    os_name = {"win32": "win32", "darwin": "darwin"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {
        "amd64": "x64",
        "x86_64": "x64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine, machine)
    return os_name, arch


def _required_string(value: Mapping[str, Any], field: str, *, source: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise PluginManifestError(f"{field} must be a non-empty string: {source}")
    return raw.strip()


def _required_int(value: Mapping[str, Any], field: str, *, source: str) -> int:
    raw = value.get(field)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PluginManifestError(f"{field} must be an integer: {source}")
    return raw


def _safe_package_path(value: str, *, field: str, source: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path == "."
        or (path.parts and path.parts[0].endswith(":"))
    ):
        raise PluginManifestError(f"{field} contains an unsafe path: {source}")
    return path.as_posix()


def _parse_platform(value: object, *, source: str) -> PluginPlatform:
    if not isinstance(value, Mapping):
        raise PluginManifestError(f"platform entries must be objects: {source}")
    return PluginPlatform(
        os=_required_string(value, "os", source=source),
        arch=_required_string(value, "arch", source=source),
    )


def _parse_entrypoints(value: object, *, source: str) -> PluginEntrypoints:
    if not isinstance(value, Mapping):
        raise PluginManifestError(f"entrypoints must be an object: {source}")
    backend = value.get("backend")
    desktop = value.get("desktop")
    parsed_backend = (
        _safe_package_path(backend.strip(), field="entrypoints.backend", source=source)
        if isinstance(backend, str) and backend.strip()
        else None
    )
    parsed_desktop = (
        _safe_package_path(desktop.strip(), field="entrypoints.desktop", source=source)
        if isinstance(desktop, str) and desktop.strip()
        else None
    )
    if parsed_backend is None and parsed_desktop is None:
        raise PluginManifestError(
            f"at least one plugin entrypoint is required: {source}"
        )
    return PluginEntrypoints(backend=parsed_backend, desktop=parsed_desktop)


def _parse_release(value: object, *, source: str) -> PluginReleaseContract:
    if not isinstance(value, Mapping):
        raise PluginManifestError(f"release must be an object: {source}")
    asset = _safe_package_path(
        _required_string(value, "asset", source=source),
        field="release.asset",
        source=source,
    )
    checksums_asset = _safe_package_path(
        _required_string(value, "checksums_asset", source=source),
        field="release.checksums_asset",
        source=source,
    )
    if "/" in asset or "/" in checksums_asset:
        raise PluginManifestError(
            f"release asset names cannot contain directories: {source}"
        )
    return PluginReleaseContract(asset=asset, checksums_asset=checksums_asset)


def _string_tuple(
    value: object,
    *,
    field: str,
    source: str,
    pattern: re.Pattern[str],
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PluginManifestError(f"{field} must be an array: {source}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not pattern.fullmatch(item.strip()):
            raise PluginManifestError(f"invalid {field} entry {item!r}: {source}")
        clean = item.strip()
        if clean in result:
            raise PluginManifestError(f"duplicate {field} entry {clean!r}: {source}")
        result.append(clean)
    return tuple(result)
