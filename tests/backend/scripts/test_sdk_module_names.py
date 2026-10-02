"""Names resolve through imports, standard-module conventions and builtins only."""

import ast

import pytest

from scripts.sdk_module_names import ModuleNames, assignments


def _qualified(module: str) -> str | None:
    tree = ast.parse(module)
    last = tree.body[-1]
    assert isinstance(last, ast.Expr)
    return ModuleNames(list(ast.walk(tree))).qualified(last.value)


@pytest.mark.parametrize(
    "module,expected",
    [
        ("from os.path import join as j\nj", "os.path.join"),
        ("import os.path as osp\nosp.join", "os.path.join"),
        ("from os import path\npath.dirname", "os.path.dirname"),
        ("import os\nos.path.join", "os.path.join"),
        ("os.getcwd", "os.getcwd"),
        ("Path.cwd", "pathlib.Path.cwd"),
        ("open", "builtins.open"),
    ],
)
def test_names_resolve_to_their_dotted_origin(module: str, expected: str) -> None:
    assert _qualified(module) == expected


@pytest.mark.parametrize(
    "module",
    [
        "join",
        "def dirname(value):\n    return value\ndirname",
        "os = load()\nos.path.join",
        "roles.asset_path",
    ],
)
def test_unbound_or_locally_bound_names_have_no_origin(module: str) -> None:
    assert _qualified(module) is None


def test_assignments_follow_source_order_and_expand_augmented_division() -> None:
    tree = ast.parse("b = 1\na = 2\na /= 'x'")
    found = [
        (name, ast.unparse(value)) for name, value in assignments(list(ast.walk(tree)))
    ]
    assert found == [("b", "1"), ("a", "2"), ("a", "a / 'x'")]
