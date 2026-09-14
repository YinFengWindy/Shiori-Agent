"""Versioned, static external package validation. No plugin modules are imported."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.manifest import ManifestError, PluginManifest, load_manifest
from agent.plugin_host.package_paths import contained_file, package_path
from agent.plugin_host.package_artifacts import validate_artifact
from agent.plugin_host.versions import SemVer
from agent.plugin_host.package_schema import (
    string_field,
    string_list,
    object_field,
    compatible_range,
)
from agent.plugin_host.renderer_contract import RendererEntry, validate_renderer


@dataclass(frozen=True)
class ValidatedPackage:
    """Static package descriptor; validation neither grants trust nor activates code."""

    manifest: PluginManifest
    runtime_api: str
    renderer: tuple[RendererEntry, ...]
    assets: tuple[str, ...]


def validate_package(
    root: Path, *, host: HostRuntimeContract | None = None
) -> ValidatedPackage:
    """Validate a directory package and every declared entry before any execution.

    Directory and zip callers share this validator. Legacy bundled manifests use
    load_manifest directly; this public external-package boundary requires v1.
    """
    _ = contained_file(root, "manifest.yaml", "manifest")
    try:
        manifest = load_manifest(root)
    except ManifestError as exc:
        raise PackageContractError("invalid_manifest", "manifest", str(exc)) from exc
    if manifest is None:
        raise PackageContractError(
            "invalid_manifest", "manifest", "Missing manifest.yaml"
        )
    raw = manifest.metadata
    allowed = {
        "api",
        "package_contract",
        "id",
        "version",
        "runtime_api",
        "entry",
        "capabilities",
        "desc",
        "author",
        "config_model",
        "dependencies",
        "optional_dependencies",
        "supports_hot_unload",
        "renderer",
        "assets",
        "host_dependencies",
        "peer_dependencies",
    }
    _ = object_field(raw, "manifest", allowed)
    if type(raw.get("package_contract")) is not int or raw["package_contract"] != 1:
        raise PackageContractError(
            "unsupported_contract", "package_contract", "Expected package_contract: 1"
        )
    if type(raw.get("api")) is not int or raw["api"] != 2:
        raise PackageContractError("invalid_manifest", "api", "Expected integer api: 2")
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
    runtime_api = compatible_range(
        runtime.runtime_api, raw.get("runtime_api"), "runtime_api"
    )
    dependencies = object_field(
        raw.get("host_dependencies", {}), "host_dependencies", {"python"}
    )
    for index, name in enumerate(
        string_list(dependencies.get("python", []), "host_dependencies.python")
    ):
        if not runtime.provides_python(name):
            raise PackageContractError(
                "missing_dependency",
                f"host_dependencies.python[{index}]",
                f"Host does not provide Python distribution {name}",
            )
    _ = validate_artifact(root, raw.get("entry"), "entry", ".py")
    renderer = validate_renderer(root, raw, runtime)
    assets = string_list(raw.get("assets", []), "assets")
    for index, path in enumerate(assets):
        _ = contained_file(root, path, f"assets[{index}]")
    return ValidatedPackage(manifest, runtime_api, renderer, assets)
