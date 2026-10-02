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
        "config = Path('bootstrap') / 'config.yaml'\ntext = config.read_text()",
        "import os\nprompt = os.path.join(os.getcwd(), 'prompts', 'system.md')",
        "entry = Path.cwd() / 'main.py'",
        "import os\nroot = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir)",
        "source = open('bootstrap/app.py').read()",
        "with open(os.path.join('prompts', 'agent.py')) as file:\n    pass",
        "root = Path(__file__).parent\nroot /= '../../..'",
        # Relative paths reaching file-system access, and string-built cwd paths.
        "import os\nnames = os.listdir('skills')",
        "import glob\nmodules = glob.glob('bootstrap/*.py')",
        "import os\nos.chdir('../../apps/backend')",
        "import os\nbackend = os.getcwd() + '/apps/backend'",
        "import sys\nsys.path.insert(0, 'apps/backend')",
    ],
)
def test_repository_layout_escapes_are_rejected(tmp_path: Path, source: str) -> None:
    owner = tmp_path / "plugins/demo"
    assert resource_edges(ast.parse(source), owner / "backend/plugin.py", owner)


@pytest.mark.parametrize(
    "source",
    [
        # Fragments appended to a plugin-owned base are not working-directory paths.
        "prompt = Path(__file__).parent / Path('prompts') / 'a.md'",
        "HERE = Path(__file__).parent\nprompt = HERE.joinpath(Path('prompts', 'a.md'))",
        "SUB = Path('utils')\nhelpers = Path(__file__).parent / SUB",
        # str() and posixpath.join build strings such as keys and URLs.
        "SCOPE = 'session'\nkey = str(SCOPE)",
        "import os\nkey = os.path.join('core', 'enabled')",
        "import posixpath\nroute = posixpath.join('agent', 'v1')",
        # A plugin test's own fixtures under tests/ are not the host test tree.
        "fixture = Path('tests') / 'fixtures' / 'x.json'",
        "root = Path(__file__).parent\nroot /= 'data'",
        # Ordinary calls receive keys or plugin-relative names, not cwd paths.
        "import os\nasset = roles.asset_path(os.path.join('prompts', 'a.md'))",
        "skill = resolve_path(str(Path('skills') / 'weather' / 'SKILL.md'), allowed_dir=ws)",
        "import os\nctx.storage.write(os.path.join('session', 'state.json'))",
        "from pathlib import PurePosixPath\nstate = z.read(str(PurePosixPath('session') / 'state.json'))",
        "prompt = ctx.resolve(Path('prompts') / 'a.md')",
        # Only genuine os.path functions build paths.
        "def dirname(value):\n    return value\nroot = dirname(dirname(dirname(__file__)))",
    ],
)
def test_plugin_paths_named_like_host_packages_are_allowed(
    tmp_path: Path, source: str
) -> None:
    owner = tmp_path / "plugins/demo"
    assert not resource_edges(ast.parse(source), owner / "backend/plugin.py", owner)


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
        "url = 'https://github.com/YinFengWindy/Shiori-Agent/tree/main/apps/backend/'\n"
        "note = 'Moved from apps/backend/ to the SDK.'\n"
        "data = 'plugins/x/tests/backend/data.json'\n"
    )
    assert not resource_edges(ast.parse(source), owner / "backend/plugin.py", owner)


@pytest.mark.parametrize(
    "source",
    [
        "config = Path.cwd() / 'apps' / 'backend' / 'config.yaml'",
        "asset = Path('apps/backend/prompts/system.md')",
        "root = Path(__file__).resolve().parents[3]",
        "source = open('bootstrap/app.py').read()",
        "source = open('apps/backend/main.py').read()",
        "import os\nbackend = os.getcwd() + '/apps/backend'",
        # Expression and sink rules see the same value.
        "text = Path('apps/backend/x.py').read_text()",
        # Paths derived from a violating path are that same violation.
        "p = Path.cwd()\np /= 'core'\np /= 'config.py'",
        "R = Path(__file__).parents[3]\na = R / 'a'\nb = a / 'b.toml'",
    ],
)
def test_each_violation_is_counted_once(tmp_path: Path, source: str) -> None:
    owner = tmp_path / "plugins/demo"
    edges = resource_edges(ast.parse(source), owner / "backend/plugin.py", owner)
    assert sum(edges.values()) == 1, edges
