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
_RPC_METHOD_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)*$")


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
class PluginToolDeclaration:
    """One allowlisted MCP tool exposed by an installed plugin backend."""

    remote_name: str
    name: str
    risk: str
    always_on: bool
    search_hint: str | None


@dataclass(frozen=True)
class PluginRpcDeclaration:
    """One backend RPC method exposed only to this plugin's desktop pages."""

    method: str
    remote_name: str


@dataclass(frozen=True)
class PluginDesktopContribution:
    """One sandboxed desktop surface contributed by an installed plugin."""

    contribution_id: str
    kind: str
    entrypoint: str
    width: int
    height: int
    transparent: bool
    always_on_top: bool
    skip_taskbar: bool
    resizable: bool
    frame: bool


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
    tools: tuple[PluginToolDeclaration, ...]
    rpc_methods: tuple[PluginRpcDeclaration, ...]
    desktop_contributions: tuple[PluginDesktopContribution, ...]
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
        tools = _parse_tools(value.get("tools", []), source=source)
        if tools and "agent.tool" not in capabilities:
            raise PluginManifestError(
                f"tools require the agent.tool capability: {source}"
            )
        if tools and entrypoints.backend is None:
            raise PluginManifestError(f"tools require a backend entrypoint: {source}")
        rpc_methods = _parse_rpc_methods(value.get("rpc_methods", []), source=source)
        if rpc_methods and "plugin.rpc" not in capabilities:
            raise PluginManifestError(
                f"rpc_methods require the plugin.rpc capability: {source}"
            )
        if rpc_methods and entrypoints.backend is None:
            raise PluginManifestError(
                f"rpc_methods require a backend entrypoint: {source}"
            )
        desktop_contributions = _parse_desktop_contributions(
            value.get("desktop_contributions", []),
            source=source,
        )
        if desktop_contributions and "desktop.overlay" not in capabilities:
            raise PluginManifestError(
                f"desktop_contributions require the desktop.overlay capability: {source}"
            )
        if desktop_contributions and entrypoints.desktop is None:
            raise PluginManifestError(
                f"desktop_contributions require a desktop entrypoint: {source}"
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
            tools=tools,
            rpc_methods=rpc_methods,
            desktop_contributions=desktop_contributions,
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
            "tools": [
                {
                    "remote_name": item.remote_name,
                    "name": item.name,
                    "risk": item.risk,
                    "always_on": item.always_on,
                    **(
                        {"search_hint": item.search_hint}
                        if item.search_hint is not None
                        else {}
                    ),
                }
                for item in self.tools
            ],
            "rpc_methods": [
                {"method": item.method, "remote_name": item.remote_name}
                for item in self.rpc_methods
            ],
            "desktop_contributions": [
                {
                    "id": item.contribution_id,
                    "kind": item.kind,
                    "entrypoint": item.entrypoint,
                    "width": item.width,
                    "height": item.height,
                    "transparent": item.transparent,
                    "always_on_top": item.always_on_top,
                    "skip_taskbar": item.skip_taskbar,
                    "resizable": item.resizable,
                    "frame": item.frame,
                }
                for item in self.desktop_contributions
            ],
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


def _parse_tools(value: object, *, source: str) -> tuple[PluginToolDeclaration, ...]:
    if not isinstance(value, list):
        raise PluginManifestError(f"tools must be an array: {source}")
    tools: list[PluginToolDeclaration] = []
    remote_names: set[str] = set()
    public_names: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise PluginManifestError(f"tool entries must be objects: {source}")
        remote_name = _required_string(raw, "remote_name", source=source)
        name = _required_string(raw, "name", source=source)
        if not _PLUGIN_ID_PATTERN.fullmatch(remote_name):
            raise PluginManifestError(
                f"invalid tool remote_name {remote_name!r}: {source}"
            )
        if not _PLUGIN_ID_PATTERN.fullmatch(name):
            raise PluginManifestError(f"invalid tool name {name!r}: {source}")
        if remote_name in remote_names or name in public_names:
            raise PluginManifestError(f"duplicate plugin tool declaration: {source}")
        risk = str(raw.get("risk") or "external-side-effect").strip()
        if risk not in {"read-only", "write", "external-side-effect"}:
            raise PluginManifestError(f"invalid tool risk {risk!r}: {source}")
        always_on = raw.get("always_on", False)
        if not isinstance(always_on, bool):
            raise PluginManifestError(f"tool always_on must be a boolean: {source}")
        raw_search_hint = raw.get("search_hint")
        if raw_search_hint is not None and (
            not isinstance(raw_search_hint, str) or not raw_search_hint.strip()
        ):
            raise PluginManifestError(f"tool search_hint must be a string: {source}")
        tools.append(
            PluginToolDeclaration(
                remote_name=remote_name,
                name=name,
                risk=risk,
                always_on=always_on,
                search_hint=(
                    raw_search_hint.strip()
                    if isinstance(raw_search_hint, str)
                    else None
                ),
            )
        )
        remote_names.add(remote_name)
        public_names.add(name)
    return tuple(tools)


def _parse_rpc_methods(
    value: object,
    *,
    source: str,
) -> tuple[PluginRpcDeclaration, ...]:
    if not isinstance(value, list):
        raise PluginManifestError(f"rpc_methods must be an array: {source}")
    declarations: list[PluginRpcDeclaration] = []
    methods: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise PluginManifestError(f"rpc method entries must be objects: {source}")
        method = _required_string(raw, "method", source=source)
        remote_name = _required_string(raw, "remote_name", source=source)
        if not _RPC_METHOD_PATTERN.fullmatch(method):
            raise PluginManifestError(f"invalid rpc method {method!r}: {source}")
        if not _PLUGIN_ID_PATTERN.fullmatch(remote_name):
            raise PluginManifestError(
                f"invalid rpc remote_name {remote_name!r}: {source}"
            )
        if method in methods:
            raise PluginManifestError(f"duplicate rpc method {method!r}: {source}")
        declarations.append(
            PluginRpcDeclaration(method=method, remote_name=remote_name)
        )
        methods.add(method)
    return tuple(declarations)


def _parse_desktop_contributions(
    value: object,
    *,
    source: str,
) -> tuple[PluginDesktopContribution, ...]:
    if not isinstance(value, list):
        raise PluginManifestError(f"desktop_contributions must be an array: {source}")
    contributions: list[PluginDesktopContribution] = []
    contribution_ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise PluginManifestError(
                f"desktop contribution entries must be objects: {source}"
            )
        contribution_id = _required_string(raw, "id", source=source)
        if not _PLUGIN_ID_PATTERN.fullmatch(contribution_id):
            raise PluginManifestError(
                f"invalid desktop contribution id {contribution_id!r}: {source}"
            )
        if contribution_id in contribution_ids:
            raise PluginManifestError(
                f"duplicate desktop contribution id {contribution_id!r}: {source}"
            )
        kind = _required_string(raw, "kind", source=source)
        if kind != "overlay":
            raise PluginManifestError(
                f"unsupported desktop contribution kind {kind!r}: {source}"
            )
        entrypoint = _safe_package_path(
            _required_string(raw, "entrypoint", source=source),
            field="desktop_contributions.entrypoint",
            source=source,
        )
        contributions.append(
            PluginDesktopContribution(
                contribution_id=contribution_id,
                kind=kind,
                entrypoint=entrypoint,
                width=_bounded_int(
                    raw, "width", source=source, minimum=64, maximum=4096
                ),
                height=_bounded_int(
                    raw, "height", source=source, minimum=64, maximum=4096
                ),
                transparent=_optional_bool(raw, "transparent", False, source=source),
                always_on_top=_optional_bool(
                    raw, "always_on_top", False, source=source
                ),
                skip_taskbar=_optional_bool(raw, "skip_taskbar", True, source=source),
                resizable=_optional_bool(raw, "resizable", False, source=source),
                frame=_optional_bool(raw, "frame", False, source=source),
            )
        )
        contribution_ids.add(contribution_id)
    return tuple(contributions)


def _bounded_int(
    value: Mapping[str, Any],
    field: str,
    *,
    source: str,
    minimum: int,
    maximum: int,
) -> int:
    result = _required_int(value, field, source=source)
    if result < minimum or result > maximum:
        raise PluginManifestError(
            f"{field} must be between {minimum} and {maximum}: {source}"
        )
    return result


def _optional_bool(
    value: Mapping[str, Any],
    field: str,
    default: bool,
    *,
    source: str,
) -> bool:
    result = value.get(field, default)
    if not isinstance(result, bool):
        raise PluginManifestError(f"{field} must be a boolean: {source}")
    return result
