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
        "import pathlib\nroot = pathlib.Path(__file__).parents[3]",
        "import pathlib\nconfig = pathlib.Path(__file__).resolve().parent.parent.parent / 'config.toml'",
        "import os\nroot = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'apps', 'backend')",
        "import os\nhere = os.path.dirname(__file__)\nconfig = os.path.join(here, '..', '..', '..', 'config.toml')",
        "config = Path(__file__).parent.joinpath('..', '..', '..', 'config.toml')",
        "config = Path.cwd() / 'apps/backend/config.yaml'",
        "import pathlib\nroot = pathlib.Path.cwd()\nconfig = root / 'apps' / 'backend' / 'config.yaml'",
        "import os\nconfig = os.path.join(os.getcwd(), 'apps', 'backend', 'config.yaml')",
        "prompts = Path('apps') / 'backend' / 'prompts'",
        "import os\nroot = os.path.join(os.path.split(__file__)[0], '..', '..', '..')",
        "import os\nroot = os.path.join(os.path.dirname(__file__), *['..', '..', '..'])",
        "import os\nroot = os.path.join(os.path.dirname(__file__), *('..', '..', '..'))",
        "root = Path(__file__).parent / ('..' + '/../..')",
        "up = '..'\nroot = Path(__file__).parent / f'{up}/{up}/{up}'",
        "config = Path.cwd() / ('apps/' + 'backend')",
        "config = Path('bootstrap') / 'config.yaml'",
        "import os\nprompt = os.path.join(os.getcwd(), 'prompts', 'system.md')",
        "entry = Path.cwd() / 'main.py'",
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


def test_plugin_owned_paths_in_attribute_os_path_and_cwd_forms_are_allowed(
    tmp_path: Path,
) -> None:
    owner = tmp_path / "plugins/demo"
    source = (
        "import os, pathlib\n"
        "root = pathlib.Path(__file__).resolve().parents[1]\n"
        "manifest = root.joinpath('manifest.yaml')\n"
        "here = os.path.dirname(os.path.abspath(__file__))\n"
        "schema = os.path.join(here, 'schemas', 'config.json')\n"
        "state = os.path.join(os.path.dirname(here), 'manifest.yaml')\n"
        "output = pathlib.Path.cwd() / 'data' / 'backend' / 'cache.json'\n"
        "name = os.path.split(__file__)[1]\n"
        "data = os.path.join(here, *['data', 'cache.json'])\n"
        "bundled = Path(__file__).parent / ('bootstrap' + '.yaml')\n"
        "fixture = Path('fixtures') / 'reply.json'\n"
        "label = ', '.join(['apps', 'backend'])\n"
    )
    assert not resource_edges(ast.parse(source), owner / "backend/plugin.py", owner)
