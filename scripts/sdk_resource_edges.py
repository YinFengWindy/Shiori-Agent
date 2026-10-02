"""Detect repository-layout resource access without rejecting plugin-owned files.

The evaluation is lexical: paths derived from ``__file__`` or the working
directory through names bound in the same module are followed, while values that
need data flow through attributes, containers or call results (for example
``self.root.parents[3]``) are not. External execution against installed wheels
backs up these known limits.
"""

import ast
import os
import re
from collections import Counter
from collections.abc import Iterator
from itertools import product
from pathlib import Path

from scripts.sdk_boundaries import host_roots
from scripts.sdk_strings import literal_strings

# Lexical stand-in for the process working directory. Paths derived from it are
# judged by their relative layout, because the working directory is unknown.
_WORKING_DIRECTORY = Path(os.path.abspath(os.sep + "__shiori_working_directory__"))
_HOST_LAYOUT = re.compile(r"(?:^|/)(?:apps/backend|apps/desktop|tests/backend)(?:/|$)")
# Top-level checkout entries a working-directory path must not start with: the
# actual host packages/modules plus the repository's own layout directories.
HOST_TOP_LEVEL = host_roots(Path(__file__).resolve().parents[1]) | {
    "apps",
    "packages",
}
_PATH_TYPES = frozenset(
    {
        "Path",
        "PurePath",
        "PosixPath",
        "WindowsPath",
        "PurePosixPath",
        "PureWindowsPath",
    }
)


def _callee(node: ast.Call) -> str | None:
    """Names ``f(...)`` and ``module.f(...)`` alike (``pathlib.Path``, ``os.path``)."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _arguments(args: list[ast.expr]) -> list[ast.expr] | None:
    """Expands ``*[...]``/``*(...)`` literals; other star arguments are unknown."""
    expanded: list[ast.expr] = []
    for arg in args:
        if isinstance(arg, ast.Starred):
            if not isinstance(arg.value, (ast.List, ast.Tuple)):
                return None
            expanded.extend(arg.value.elts)
        else:
            expanded.append(arg)
    return expanded


class _Evaluator:
    """Possible values of path expressions within one module."""

    def __init__(self, source: Path, strings: dict[str, set[str]]) -> None:
        self.source = source
        self.strings = strings
        self.paths: dict[str, set[Path]] = {}

    def join(self, bases: set[Path], parts: list[ast.expr]) -> set[Path]:
        """Joins string-valued components lexically; unknown components stop."""
        values = [literal_strings(part, self.strings) for part in parts]
        if not all(values):
            return set()
        joined: set[Path] = set()
        for base, names in product(bases, product(*values)):
            if any(os.path.isabs(name) or Path(name).anchor for name in names):
                continue
            joined.add(Path(os.path.normpath(base.joinpath(*names))))
        return joined

    def argument(self, node: ast.expr) -> set[Path]:
        """A path argument: a derived path, or a relative string (working directory)."""
        return self.join({_WORKING_DIRECTORY}, [node]) | self.evaluate(node)

    def call(self, node: ast.Call) -> set[Path]:
        name = _callee(node)
        args = _arguments(node.args)
        if args is None:
            return set()
        if name in _PATH_TYPES:
            # Path() is the working directory; Path(a, "b") joins like os.path.join.
            if not args:
                return {_WORKING_DIRECTORY}
            return self.join(self.argument(args[0]), args[1:])
        if name in {"cwd", "getcwd"} and not args:
            return {_WORKING_DIRECTORY}
        if isinstance(node.func, ast.Attribute) and name in {
            "resolve",
            "absolute",
            "expanduser",
        }:
            return self.evaluate(node.func.value)
        if isinstance(node.func, ast.Attribute) and name == "joinpath":
            return self.join(self.evaluate(node.func.value), args)
        if not args:
            return set()
        if name in {"abspath", "realpath", "normpath", "str", "fspath"}:
            return self.argument(args[0])
        if name == "dirname":
            return {path.parent for path in self.argument(args[0])}
        # os.path.join(...), but never str.join on a literal separator.
        if name == "join" and not (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Constant)
        ):
            return self.join(self.argument(args[0]), args[1:])
        return set()

    def subscript(self, node: ast.Subscript) -> set[Path]:
        if not (
            isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int)
        ):
            return set()
        index = node.slice.value
        if isinstance(node.value, ast.Attribute) and node.value.attr == "parents":
            return {
                path.parents[index]
                for path in self.evaluate(node.value.value)
                if 0 <= index < len(path.parents)
            }
        # os.path.split(path)[0] is the directory; [1] is a file name.
        if (
            index == 0
            and isinstance(node.value, ast.Call)
            and _callee(node.value) == "split"
            and len(node.value.args) == 1
        ):
            return {path.parent for path in self.evaluate(node.value.args[0])}
        return set()

    def evaluate(self, node: ast.AST) -> set[Path]:
        """Every path ``node`` can denote; empty when it is not a known path."""
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return {self.source}
            return self.paths.get(node.id, set())
        if isinstance(node, ast.Call):
            return self.call(node)
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            return {path.parent for path in self.evaluate(node.value)}
        if isinstance(node, ast.Subscript):
            return self.subscript(node)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self.join(self.evaluate(node.left), [node.right])
        return set()


def _assignments(nodes: list[ast.AST]) -> Iterator[tuple[str, ast.expr]]:
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.value


def _host_layout(relative: str, host_top_level: frozenset[str]) -> bool:
    """Whether a working-directory path assumes the process runs in a checkout."""
    first = relative.split("/")[0]
    module = first.rsplit(".", 1)[0] if first.endswith((".py", ".pyi")) else first
    return module in host_top_level or bool(_HOST_LAYOUT.search(relative))


def resource_edges(
    tree: ast.AST,
    source: Path,
    owner: Path,
    host_top_level: frozenset[str] = HOST_TOP_LEVEL,
) -> Counter[str]:
    """Reject host-layout paths derived from source ancestors or the working directory.

    ``source`` and ``owner`` must be normalized the same way (both resolved).
    Paths below the owning SDK/plugin package stay allowed.
    """
    edges: Counter[str] = Counter()
    nodes = list(ast.walk(tree))
    parents = {
        child: parent for parent in nodes for child in ast.iter_child_nodes(parent)
    }
    # String values are folded once in source order (as the import guard does);
    # conditional assignments keep every possible value.
    strings: dict[str, set[str]] = {}
    for name, value in _assignments(nodes):
        strings.setdefault(name, set()).update(literal_strings(value, strings))
    evaluator = _Evaluator(source, strings)
    # Resolve simple path aliases until stable, including aliases used earlier in
    # function bodies. This is a lint check, not a sandbox for arbitrary Python.
    for _ in range(len(nodes)):
        changed = False
        for name, value in _assignments(nodes):
            paths = evaluator.evaluate(value)
            if paths and evaluator.paths.get(name) != paths:
                evaluator.paths[name] = paths
                changed = True
        if not changed:
            break
    for node in nodes:
        for value in evaluator.evaluate(node):
            if value.is_relative_to(_WORKING_DIRECTORY):
                relative = value.relative_to(_WORKING_DIRECTORY).as_posix()
                if _host_layout(relative, host_top_level):
                    edges[f"repository resource via working directory: {relative}"] += 1
            elif not value.is_relative_to(owner):
                edges["repository-layout path outside owning package"] += 1
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parent = parents.get(node)
            # Documentation is not file access. Explicit fixture/runtime path
            # inputs (tmp_path / "...") are also independent of source layout;
            # working-directory joins are judged as paths above.
            if isinstance(parent, ast.Expr) or (
                isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div)
            ):
                continue
            normalized = node.value.replace("\\", "/")
            if any(
                part in normalized
                for part in ("apps/backend/", "tests/backend/", "apps/desktop/")
            ):
                edges[f"repository resource: {node.value}"] += 1
    return edges
