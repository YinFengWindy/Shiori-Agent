"""import-linter contract: a plugin imports only the plugins its manifest declares.

Declared means the plugin itself plus ``dependencies`` and ``optional_dependencies``
of ``plugins/<id>/manifest.yaml``. The manifests stay the single source, so the
contract needs no per-plugin configuration. Only direct imports are checked.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from grimp import ImportGraph
from importlinter import Contract, ContractCheck, output

ROOT = Path(__file__).resolve().parents[1]
PLUGINS_PACKAGE = "plugins"


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
            for detail in graph.get_import_details(
                importer=importer, imported=imported
            ):
                found.append(
                    {
                        "importer": importer,
                        "imported": imported,
                        "line_number": detail["line_number"],
                    }
                )
    return found


class ManifestDependencyContract(Contract):
    """Reports plugin-to-plugin imports missing from the importer's manifest."""

    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        found = undeclared_imports(graph, declared_plugins(ROOT / PLUGINS_PACKAGE))
        return ContractCheck(kept=not found, metadata={"imports": found})

    def render_broken_contract(self, check: ContractCheck) -> None:
        for item in check.metadata["imports"]:
            output.print_error(
                f"-   {item['importer']} -> {item['imported']} "
                f"(l.{item['line_number']}): not declared in the manifest",
                bold=False,
            )
        output.new_line()
