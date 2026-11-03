"""Static external package validation. No plugin modules are imported.

Install accepts only ``api: 4``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from shiori_sdk.kernel import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.manifest import (
    IncompatibleSdkError,
    ManifestError,
    PluginManifest,
    UnsupportedApiError,
    load_manifest,
    require_compatible_sdk,
)
from agent.plugin_host.package_paths import contained_file, package_path
from agent.plugin_host.package_artifacts import validate_artifact
from agent.plugin_host.versions import SemVer
from agent.plugin_host.package_schema import (
    string_field,
    string_list,
    object_field,
)
from agent.plugin_host.frontend_contract import FrontendEntry, validate_frontend

# External API 4 packages declare one frontend entry.
_PACKAGE_FIELDS = {
    "api",
    "id",
    "display_name",
    "distribution",
    "category",
    "default_enabled",
    "version",
    "sdk",
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
}


@dataclass(frozen=True)
class ValidatedPackage:
    """Static package descriptor; validation neither grants trust nor activates code."""

    manifest: PluginManifest
    frontend: FrontendEntry | None
    assets: tuple[str, ...]


def validate_package(
    root: Path, *, host: HostRuntimeContract | None = None
) -> ValidatedPackage:
    """Validate an ``api: 4`` directory package before any plugin code runs.

    Directory and zip callers share this validator. Anything that is not
    integer ``api: 4`` is rejected here, before the trust prompt. Bundled
    plugins use ``load_manifest`` directly.
    """
    _ = contained_file(root, "manifest.yaml", "manifest")
    try:
        manifest = load_manifest(root)
    except UnsupportedApiError as exc:
        raise PackageContractError("unsupported_api", "api", str(exc)) from exc
    except ManifestError as exc:
        raise PackageContractError("invalid_manifest", "manifest", str(exc)) from exc
    if manifest is None:
        raise PackageContractError(
            "invalid_manifest", "manifest", "Missing manifest.yaml"
        )
    try:
        require_compatible_sdk(manifest.sdk)
    except IncompatibleSdkError as exc:
        raise PackageContractError("incompatible_sdk", "sdk", str(exc)) from exc
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
    frontend = validate_frontend(root, raw, runtime)
    assets = string_list(raw.get("assets", []), "assets")
    for index, path in enumerate(assets):
        _ = contained_file(root, path, f"assets[{index}]")
    return ValidatedPackage(manifest, frontend, assets)
