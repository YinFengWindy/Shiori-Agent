"""Static external package validation. No plugin modules are imported.

Install accepts only ``api: 4``. ``runtime_api`` ranges and ``package_contract``
are not consulted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from shiori_sdk.kernel import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.manifest import (
    UNSUPPORTED_API_REASON,
    ManifestError,
    PluginManifest,
    load_manifest,
)
from agent.plugin_host.package_paths import contained_file, package_path
from agent.plugin_host.package_artifacts import validate_artifact
from agent.plugin_host.versions import SemVer
from agent.plugin_host.package_schema import (
    string_field,
    string_list,
    object_field,
)
from agent.plugin_host.renderer_contract import RendererEntry, validate_renderer

# api: 4 external packages. ``renderer`` stays until the frontend migration;
# ``runtime_api``, ``package_contract``, ``capabilities`` and ``host_dependencies`` do not.
_PACKAGE_FIELDS = {
    "api",
    "id",
    "display_name",
    "distribution",
    "category",
    "default_enabled",
    "version",
    "entry",
    "desc",
    "author",
    "config_model",
    "dependencies",
    "optional_dependencies",
    "inject",
    "optional_inject",
    "provides",
    "supports_hot_unload",
    "contributes",
    "frontend",
    "assets",
    "renderer",
    "peer_dependencies",
}


@dataclass(frozen=True)
class ValidatedPackage:
    """Static package descriptor; validation neither grants trust nor activates code."""

    manifest: PluginManifest
    runtime_api: str
    renderer: tuple[RendererEntry, ...]
    assets: tuple[str, ...]


def _unsupported_api(exc: Exception | None = None) -> PackageContractError:
    error = PackageContractError("unsupported_api", "api", UNSUPPORTED_API_REASON)
    if exc is not None:
        raise error from exc
    return error


def validate_package(
    root: Path, *, host: HostRuntimeContract | None = None
) -> ValidatedPackage:
    """Validate an ``api: 4`` directory package before any plugin code runs.

    Directory and zip callers share this validator. Anything that is not
    integer ``api: 4`` is rejected here, before the trust prompt. Bundled
    plugins use ``load_manifest`` directly and are blocked at discovery.
    """
    _ = contained_file(root, "manifest.yaml", "manifest")
    try:
        manifest = load_manifest(root)
    except ManifestError as exc:
        api = (exc.metadata or {}).get("api")
        if type(api) is int and api == 4:
            raise PackageContractError(
                "invalid_manifest", "manifest", str(exc)
            ) from exc
        raise _unsupported_api(exc)
    if manifest is None:
        raise PackageContractError(
            "invalid_manifest", "manifest", "Missing manifest.yaml"
        )
    if manifest.api != 4:
        raise _unsupported_api()
    raw = manifest.metadata
    _ = object_field(raw, "manifest", _PACKAGE_FIELDS)
    plugin_id = string_field(raw.get("id"), "id")
    if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", plugin_id) is None:
        raise PackageContractError(
            "invalid_manifest", "id", "Expected a lowercase portable plugin ID"
        )
    _ = package_path(plugin_id, "id")
    version = string_field(raw.get("version"), "version")
    try:
        _ = SemVer.parse(version)
    except ValueError as exc:
        raise PackageContractError("invalid_version", "version", str(exc)) from exc
    runtime = host or HostRuntimeContract()
    _ = validate_artifact(root, raw.get("entry"), "entry", ".py")
    renderer: tuple[RendererEntry, ...] = ()
    if "renderer" in raw:
        renderer = validate_renderer(root, raw, runtime)
    assets = string_list(raw.get("assets", []), "assets")
    for index, path in enumerate(assets):
        _ = contained_file(root, path, f"assets[{index}]")
    return ValidatedPackage(manifest, "", renderer, assets)
