"""Plugin-to-plugin imports are judged against the importer's manifest."""

from pathlib import Path

import pytest
from grimp import ImportGraph

from scripts.plugin_import_contract import declared_plugins, undeclared_imports


def test_only_imports_missing_from_the_importer_manifest_are_reported(
    tmp_path: Path,
) -> None:
    for plugin, manifest in {
        "story": "dependencies: [novelai]\n",
        "status": "optional_dependencies: [observe]\n",
        "novelai": "",
        "observe": "",
    }.items():
        (tmp_path / plugin).mkdir()
        (tmp_path / plugin / "manifest.yaml").write_text(
            f"id: {plugin}\n{manifest}", encoding="utf-8"
        )
    graph = ImportGraph()
    for module in (
        "plugins",
        "plugins.story.plugin",
        "plugins.status.plugin",
        "plugins.novelai.api",
        "plugins.observe.api",
    ):
        graph.add_module(module)
    for importer, imported, line in (
        ("plugins.story.plugin", "plugins.novelai.api", 1),
        ("plugins.status.plugin", "plugins.observe.api", 2),
        # Declared by story, not by novelai: dependencies are not symmetric.
        ("plugins.novelai.api", "plugins.story.plugin", 3),
    ):
        graph.add_import(
            importer=importer,
            imported=imported,
            line_number=line,
            line_contents=f"import {imported}",
        )

    assert undeclared_imports(graph, declared_plugins(tmp_path)) == [
        {
            "importer": "plugins.novelai.api",
            "imported": "plugins.story.plugin",
            "line_number": 3,
        }
    ]


def test_a_plugins_directory_without_manifest_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "story").mkdir()
    (tmp_path / "story" / "manifest.yaml").write_text("id: story\n", encoding="utf-8")
    graph = ImportGraph()
    for module in ("plugins", "plugins.story.plugin", "plugins.shared.util"):
        graph.add_module(module)

    with pytest.raises(ValueError, match="plugins/shared .* no manifest.yaml"):
        undeclared_imports(graph, declared_plugins(tmp_path))
