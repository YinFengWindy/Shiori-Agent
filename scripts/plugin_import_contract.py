"""Custom import-linter contracts for the plugin layers.

``manifest_dependencies``: a plugin imports only the plugins its manifest
declares, meaning the plugin itself plus ``dependencies`` and
``optional_dependencies`` of ``plugins/<id>/manifest.yaml``. The manifests stay
the single source, so the contract needs no per-plugin configuration.

``kernel_isolation``: ``shiori_sdk.kernel`` imports only its own modules and
the standard library, so it knows no business, no core contract and no
third-party package (refactor plan §5.4, D3).

Only direct imports are checked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from grimp import ImportGraph
from importlinter import Contract, ContractCheck, output

ROOT = Path(__file__).resolve().parents[1]
PLUGINS_PACKAGE = "plugins"
KERNEL_PACKAGE = "shiori_sdk.kernel"


def _import_lines(
    graph: ImportGraph, importer: str, imported: str
) -> list[dict[str, object]]:
    """One report row per source line where ``importer`` imports ``imported``."""
    return [
        {
            "importer": importer,
            "imported": imported,
            "line_number": detail["line_number"],
        }
        for detail in graph.get_import_details(importer=importer, imported=imported)
    ]


def _render(check: ContractCheck, problem: str) -> None:
    for item in check.metadata["imports"]:
        output.print_error(
            f"-   {item['importer']} -> {item['imported']} "
            f"(l.{item['line_number']}): {problem}",
            bold=False,
        )
    output.new_line()


def declared_plugins(plugins_dir: Path) -> dict[str, frozenset[str]]:
    """Maps each plugin directory to the plugin directories it may import."""
    declared: dict[str, frozenset[str]] = {}
    for manifest in sorted(plugins_dir.glob("*/manifest.yaml")):
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        plugin = manifest.parent.name
        declared[plugin] = frozenset(
            {
                plugin,
                *raw.get("dependencies", []),
                *raw.get("optional_dependencies", []),
            }
        )
    return declared


def undeclared_imports(
    graph: ImportGraph, declared: dict[str, frozenset[str]]
) -> list[dict[str, object]]:
    """Direct imports from one plugin into another plugin it does not declare.

    Raises ``ValueError`` for a module below a plugins directory without a
    manifest: its allowed imports are unknown, so it cannot be judged.
    """
    found: list[dict[str, object]] = []
    for importer in sorted(graph.find_descendants(PLUGINS_PACKAGE)):
        owner = importer.split(".")[1]
        if owner not in declared:
            raise ValueError(
                f"{PLUGINS_PACKAGE}/{owner} holds module {importer} "
                "but has no manifest.yaml"
            )
        for imported in sorted(graph.find_modules_directly_imported_by(importer)):
            parts = imported.split(".")
            if parts[0] != PLUGINS_PACKAGE or len(parts) < 2:
                continue
            if parts[1] in declared[owner]:
                continue
            found.extend(_import_lines(graph, importer, imported))
    return found


class ManifestDependencyContract(Contract):
    """Reports plugin-to-plugin imports missing from the importer's manifest."""

    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        found = undeclared_imports(graph, declared_plugins(ROOT / PLUGINS_PACKAGE))
        return ContractCheck(kept=not found, metadata={"imports": found})

    def render_broken_contract(self, check: ContractCheck) -> None:
        _render(check, "not declared in the manifest")


def kernel_escapes(
    graph: ImportGraph, kernel: str = KERNEL_PACKAGE
) -> list[dict[str, object]]:
    """Direct imports from the kernel package to anything but itself and the stdlib.

    Third-party packages only appear when the graph includes external packages.
    """
    found: list[dict[str, object]] = []
    for importer in sorted({kernel, *graph.find_descendants(kernel)}):
        for imported in sorted(graph.find_modules_directly_imported_by(importer)):
            if imported == kernel or imported.startswith(kernel + "."):
                continue
            if imported.split(".")[0] in sys.stdlib_module_names:
                continue
            found.extend(_import_lines(graph, importer, imported))
    return found


class KernelIsolationContract(Contract):
    """Reports kernel imports that leave the kernel package and the stdlib."""

    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        found = kernel_escapes(graph)
        return ContractCheck(kept=not found, metadata={"imports": found})

    def render_broken_contract(self, check: ContractCheck) -> None:
        _render(check, "the kernel imports only itself and the standard library")
