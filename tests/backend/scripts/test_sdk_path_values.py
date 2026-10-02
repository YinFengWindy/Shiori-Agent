"""Path values follow import-bound path functions and explicit anchors only."""

import ast
from pathlib import Path

import pytest

from scripts.sdk_path_values import PathValues, anchored

SOURCE = Path("/repo/plugins/demo/backend/plugin.py").resolve()


def _values(module: str) -> set[Path]:
    """Values of the module's last expression statement."""
    tree = ast.parse(module)
    last = tree.body[-1]
    assert isinstance(last, ast.Expr)
    return PathValues(tree, SOURCE).evaluate(last.value)


@pytest.mark.parametrize(
    "module",
    [
        "from os.path import join as j, dirname\nj(dirname(__file__), 'x')",
        "import os.path as osp\nosp.join(osp.dirname(__file__), 'x')",
        "from os import path\npath.join(path.dirname(__file__), 'x')",
        "import ntpath\nntpath.join(ntpath.dirname(__file__), 'x')",
    ],
)
def test_import_bound_os_path_functions_are_followed(module: str) -> None:
    assert _values(module) == {SOURCE.parent / "x"}


@pytest.mark.parametrize(
    "module",
    [
        "join(dirname(__file__), 'x')",
        "import posixpath\nposixpath.join('agent', 'v1')",
        "from pathlib import PurePosixPath\nPurePosixPath('session') / 'state.json'",
        "SCOPE = 'session'\nstr(SCOPE)",
    ],
)
def test_unbound_names_pure_paths_and_strings_are_not_paths(module: str) -> None:
    assert _values(module) == set()


def test_working_directory_anchors_include_string_concatenation() -> None:
    (value,) = _values("import os\nos.getcwd() + '/apps/backend'")
    assert anchored(value) == ("cwd", "apps/backend")
    (value,) = _values("from pathlib import Path\nPath() / 'x'")
    assert anchored(value) == ("cwd", "x")


def test_relative_escapes_keep_their_anchor_and_augmented_assignment_applies_once() -> (
    None
):
    (value,) = _values("from pathlib import Path\nPath('../../apps') / 'backend'")
    assert anchored(value) == ("relative", "apps/backend")
    assert _values("root = Path(__file__).parent\nroot /= 'data'\nroot") == {
        SOURCE.parent / "data"
    }
