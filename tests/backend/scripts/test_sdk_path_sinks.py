"""Only file-system operations make a relative path cwd-rooted."""

import ast
from pathlib import Path

import pytest

from scripts.sdk_path_sinks import sink_paths
from scripts.sdk_path_values import PathValues


def _sinks(module: str) -> list[str]:
    tree = ast.parse(module)
    values = PathValues(tree, Path("/repo/plugins/demo/backend/plugin.py").resolve())
    return [
        ast.unparse(path)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for path in sink_paths(node, values)
    ]


@pytest.mark.parametrize(
    "module,expected",
    [
        ("open('a')", ["'a'"]),
        ("import io\nio.open('a')", ["'a'"]),
        ("from os import listdir\nlistdir('a')", ["'a'"]),
        ("import glob\nglob.iglob('a/*')", ["'a/*'"]),
        ("import shutil\nshutil.copy('a', 'b')", ["'a'", "'b'"]),
        ("import sys\nsys.path.insert(0, 'a')", ["'a'"]),
        ("import ntpath\nntpath.exists('a')", ["'a'"]),
        ("Path('a').read_text()", ["Path('a')"]),
    ],
)
def test_file_system_operations_are_sinks(module: str, expected: list[str]) -> None:
    assert _sinks(module) == expected


@pytest.mark.parametrize(
    "module",
    [
        "roles.asset_path('a')",
        "ctx.storage.write('a')",
        "ctx.resolve(Path('a'))",
        "z.read('a')",
        "z.open('a')",
        "from pathlib import PurePosixPath\nPurePosixPath('a').exists()",
    ],
)
def test_ordinary_calls_are_not_sinks(module: str) -> None:
    assert _sinks(module) == []
