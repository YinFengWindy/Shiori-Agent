"""Plugin-local resources are portable; deriving host paths from source depth is not."""

import ast
from pathlib import Path

import pytest

from scripts.sdk_resource_edges import resource_edges


@pytest.mark.parametrize(
    "source",
    [
        "ROOT = Path(__file__).resolve().parents[3]\nfile = ROOT / 'config/config.toml'",
        "base = Path(__file__).parent\nroot = base.parent.parent.parent",
        "root = Path(__file__).parent / '../../../apps/backend'",
        "asset = Path('apps/backend/prompts/system.md')",
        "asset = 'tests/backend/agent/fixtures.json'",
    ],
)
def test_repository_layout_escapes_are_rejected(tmp_path: Path, source: str) -> None:
    owner = tmp_path / "plugins/demo"
    assert resource_edges(ast.parse(source), owner / "backend/plugin.py", owner)


def test_plugin_owned_resources_and_explicit_sibling_resources_are_allowed(
    tmp_path: Path,
) -> None:
    owner = tmp_path / "plugins/demo"
    source = "root = Path(__file__).resolve().parents[1]\nasset = root / 'manifest.yaml'\nother = plugin_directory('citation')"
    assert not resource_edges(ast.parse(source), owner / "backend/plugin.py", owner)
