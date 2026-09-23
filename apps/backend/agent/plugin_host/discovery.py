"""Static discovery and admission for host-owned and workspace plugin roots."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from agent.plugin_host.diagnostics import PackageContractError, PluginDiagnostic
from agent.plugin_host.handle import PluginRecord
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.manifest import ManifestError, PluginManifest, load_manifest
from agent.plugin_host.package_contract import validate_package
from agent.plugin_host.package_paths import contained_file
from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trust_store import PluginTrustStore

logger = logging.getLogger(__name__)


def discover_plugins(
    roots: list[Path],
    *,
    external_roots: list[Path],
    namespace: str,
    strict: bool,
    host: HostRuntimeContract | None,
    trust: PluginTrustStore | None = None,
) -> list[PluginRecord]:
    """Keep every candidate, then reject every participant in an ID or channel conflict.

    Host-owned roots are admitted by classification. Workspace packages additionally
    require persisted approval of their exact content; IDs and enable flags cannot grant it.
    """
    external = {root.absolute() for root in external_roots}
    records: list[PluginRecord] = []
    seen: set[Path] = set()
    for root in roots:
        root = root.absolute()
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        source = "workspace" if root in external else "builtin"
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            record = _read_candidate(
                child, root, source, namespace, strict, host, trust
            )
            if record is None:
                continue
            records.append(record)
    by_id: dict[str, list[PluginRecord]] = defaultdict(list)
    for record in records:
        by_id[record.manifest.id].append(record)
    for plugin_id, candidates in by_id.items():
        if len(candidates) < 2:
            continue
        paths = "; ".join(str(record.plugin_dir) for record in candidates)
        for record in candidates:
            record.admission = PluginDiagnostic(
                "duplicate_id",
                "discovery",
                "id",
                f"插件 ID {plugin_id} 冲突：{paths}",
                str(record.plugin_dir),
                "CONFLICT",
            )
    _check_channel_conflicts(records)
    _check_external_dependencies(records, by_id)
    return records


def _check_channel_conflicts(records: list[PluginRecord]) -> None:
    """Rejects every plugin that declares a channel name another plugin also declares.

    Channel names key role bindings and conversation threads, so the host must not
    pick a winner. Candidates sharing one plugin ID are already ID conflicts.
    """
    claimants: dict[str, list[PluginRecord]] = defaultdict(list)
    for record in records:
        for declaration in record.manifest.channels:
            claimants[declaration.name].append(record)
    for channel, candidates in claimants.items():
        plugin_ids = sorted({record.manifest.id for record in candidates})
        if len(plugin_ids) < 2:
            continue
        for record in candidates:
            if record.admission is not None and record.admission.code == "duplicate_id":
                continue
            record.admission = PluginDiagnostic(
                "duplicate_channel",
                "discovery",
                "channels",
                f"渠道 {channel} 被多个插件声明：{', '.join(plugin_ids)}",
                str(record.plugin_dir),
                "CONFLICT",
            )


def _check_external_dependencies(
    records: list[PluginRecord],
    by_id: dict[str, list[PluginRecord]],
) -> None:
    # Inspection must not load even a trusted dependency on behalf of an
    # untrusted package. Required unavailable providers are still diagnosable.
    for record in records:
        if record.admission is None or record.admission.state != "UNTRUSTED":
            continue
        for index, dependency in enumerate(record.manifest.dependencies):
            targets = by_id.get(dependency, [])
            if len(targets) == 1 and targets[0].admission is None:
                continue
            record.admission = PluginDiagnostic(
                "dependency_unavailable" if targets else "missing_dependency",
                "dependency",
                f"dependencies[{index}]",
                f"插件 {record.manifest.id} 的依赖 {dependency} 不可用",
                str(record.plugin_dir),
            )
            break


def _read_candidate(
    child: Path,
    root: Path,
    source: str,
    namespace: str,
    strict: bool,
    host: HostRuntimeContract | None,
    trust: PluginTrustStore | None,
) -> PluginRecord | None:
    diagnostic: PluginDiagnostic | None = None
    fingerprint: str | None = None
    trust_directory = ""
    content_hashes: dict[str, str] = {}
    try:
        # Reject links before reading even the manifest: its contents and
        # identity are untrusted until both directory boundaries are checked.
        if not child.resolve().is_relative_to(root.resolve()):
            raise PackageContractError(
                "outside_root",
                "directory",
                "插件目录指向发现根目录之外",
                path=str(child),
            )
        manifest_path = child / "manifest.yaml"
        if source == "workspace" and (
            manifest_path.exists() or manifest_path.is_symlink()
        ):
            _ = contained_file(child, "manifest.yaml", "manifest")
        manifest = load_manifest(child)
    except PackageContractError as exc:
        manifest = PluginManifest(id=child.name)
        diagnostic = exc.diagnostic
    except ManifestError as exc:
        logger.warning("插件 manifest 无效: %s (%s)", child.name, exc)
        if source == "builtin" and strict:
            raise
        metadata = exc.metadata or {}
        if source == "builtin" and "package_contract" not in metadata:
            return None
        manifest = PluginManifest(
            id=str(metadata.get("id") or child.name),
            version=str(metadata.get("version") or ""),
            metadata=metadata,
        )
        diagnostic = PluginDiagnostic(
            "invalid_manifest",
            "validation",
            "manifest",
            str(exc),
            str(child / "manifest.yaml"),
        )
    if manifest is None:
        # Old workspace/plugins/<id>/kv.json directories are data, not packages.
        return None
    if diagnostic is None and (
        source == "workspace" or "package_contract" in manifest.metadata
    ):
        try:
            validate_package(child, host=host)
        except PackageContractError as exc:
            diagnostic = exc.diagnostic
    if diagnostic is None and source == "workspace":
        try:
            content = inspect_package_content(child)
            fingerprint = content.fingerprint
            trust_directory = content.directory
            content_hashes = content.hashes
        except PackageContractError as exc:
            diagnostic = exc.diagnostic
        if (
            diagnostic is None
            and fingerprint is not None
            and (
                trust is None
                or not trust.is_trusted(child, fingerprint, activation=True)
            )
        ):
            diagnostic = PluginDiagnostic(
                "trust_required",
                "trust",
                "source",
                "外部插件尚未获得信任",
                str(child),
                "UNTRUSTED",
            )
    return PluginRecord(
        name=child.name,
        plugin_dir=child,
        entry_file=child / manifest.entry,
        import_path=f"akasic_plugin_{namespace}_{manifest.id}",
        manifest=manifest,
        source=source,
        admission=diagnostic,
        fingerprint=fingerprint,
        trust_directory=trust_directory,
        content_hashes=content_hashes,
    )
