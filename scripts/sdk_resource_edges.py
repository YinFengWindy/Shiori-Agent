"""Detect repository-layout resource access without rejecting plugin-owned files.

The evaluation is lexical: paths derived from ``__file__``, the working directory
or relative literals are followed through names bound in the same module. Values
that need data flow through attributes, containers, call results or loops (for
example ``self.root.parents[3]``, ``parents[-1]``, ``__spec__.origin``,
``sys.path[0]`` or repeated ``dirname`` in a loop) are not; external execution
against installed wheels backs up these known limits.
"""

import ast
import os
from collections import Counter
from collections.abc import Iterator
from itertools import product
from pathlib import Path

from scripts.sdk_strings import literal_strings

# Lexical stand-ins. Paths explicitly anchored at the working directory live
# below _WORKING_DIRECTORY; bare relative literals (``Path("x")``, ``open("x")``)
# live below _RELATIVE until their use decides whether they are cwd-rooted.
_SENTINEL = Path(os.path.abspath(os.sep + "__shiori_layout__"))
_WORKING_DIRECTORY = _SENTINEL / "cwd"
_RELATIVE = _SENTINEL / "relative"
HOST_BACKEND = Path(__file__).resolve().parents[1] / "apps/backend"
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
# ``os.pardir`` / ``os.curdir`` are path components, not opaque attributes.
_PATH_CONSTANTS = {"pardir": "..", "curdir": "."}


def _callee(node: ast.Call) -> str | None:
    """Names ``f(...)`` and ``module.f(...)`` alike (``pathlib.Path``, ``os.path``)."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _os_path(node: ast.Call) -> bool:
    """``os.path.f(...)``, ``path.f(...)`` or an imported ``f(...)``; not posixpath."""
    func = node.func
    if isinstance(func, ast.Name):
        return True
    if not isinstance(func, ast.Attribute):
        return False
    owner = func.value
    return (isinstance(owner, ast.Attribute) and owner.attr == "path") or (
        isinstance(owner, ast.Name) and owner.id == "path"
    )


def _working_directory(node: ast.Call) -> bool:
    """``Path.cwd()``, ``pathlib.Path.cwd()``, ``os.getcwd()`` or ``getcwd()``."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "getcwd"
    if not isinstance(func, ast.Attribute):
        return False
    owner = func.value
    owner_name = (
        owner.id
        if isinstance(owner, ast.Name)
        else owner.attr if isinstance(owner, ast.Attribute) else None
    )
    return (func.attr == "cwd" and owner_name in _PATH_TYPES) or (
        func.attr == "getcwd" and owner_name == "os"
    )


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


def _fragments(node: ast.AST) -> list[ast.expr]:
    """Operands appended to a base path; they are never judged on their own."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return [node.right]
    if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Div):
        return [node.value]
    if isinstance(node, ast.Call):
        args = _arguments(node.args) or []
        name = _callee(node)
        if name == "joinpath":
            return args
        if name in _PATH_TYPES or (name == "join" and _os_path(node)):
            return args[1:]
    return []


class _Evaluator:
    """Possible values of path expressions within one module."""

    def __init__(self, source: Path, strings: dict[str, set[str]]) -> None:
        self.source = source
        self.strings = strings
        self.paths: dict[str, set[Path]] = {}

    def texts(self, node: ast.expr) -> set[str]:
        """Relative component values: folded strings or relative path values."""
        if isinstance(node, ast.Attribute) and node.attr in _PATH_CONSTANTS:
            return {_PATH_CONSTANTS[node.attr]}
        values = literal_strings(node, self.strings)
        if values:
            return values
        paths = self.evaluate(node)
        if paths and all(path.is_relative_to(_RELATIVE) for path in paths):
            return {path.relative_to(_RELATIVE).as_posix() for path in paths}
        return set()

    def join(self, bases: set[Path], parts: list[ast.expr]) -> set[Path]:
        """Joins relative components lexically; unknown components stop."""
        values = [self.texts(part) for part in parts]
        if not all(values):
            return set()
        joined: set[Path] = set()
        for base, names in product(bases, product(*values)):
            if any(os.path.isabs(name) or Path(name).anchor for name in names):
                continue
            joined.add(Path(os.path.normpath(base.joinpath(*names))))
        return joined

    def argument(self, node: ast.expr) -> set[Path]:
        """A path argument: a derived path, or a relative literal."""
        return self.join({_RELATIVE}, [node]) or self.evaluate(node)

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
        if not args and _working_directory(node):
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
        if name == "open" and isinstance(node.func, ast.Name):
            return self.argument(args[0])
        if not _os_path(node):
            return set()
        if name in {"abspath", "realpath", "normpath", "fspath"}:
            return self.argument(args[0])
        if name == "dirname":
            return {path.parent for path in self.argument(args[0])}
        if name == "join":
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
    """Name assignments in source order; ``p /= x`` is ``p = p / x``."""
    ordered = sorted(
        (node for node in nodes if isinstance(node, ast.stmt)),
        key=lambda node: (node.lineno, node.col_offset),
    )
    for node in ordered:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.value
        elif (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Div)
            and isinstance(node.target, ast.Name)
        ):
            name = ast.Name(id=node.target.id, ctx=ast.Load())
            yield node.target.id, ast.BinOp(left=name, op=ast.Div(), right=node.value)


def _self_referential(name: str, value: ast.expr) -> bool:
    return any(
        isinstance(child, ast.Name) and child.id == name for child in ast.walk(value)
    )


def host_layout(relative: str, backend: Path = HOST_BACKEND) -> bool:
    """Whether a checkout-relative path names the actual host layout.

    ``apps/`` and ``tests/backend/`` are repository layout. Otherwise the path
    must exist below the host backend, or name a file (it has a suffix) inside
    an existing host package directory: ``bootstrap/x.yaml`` matches while a
    configuration key such as ``core/enabled`` does not.
    """
    parts = Path(relative).parts
    if not parts or parts[0] in {".", ".."}:
        return False
    if parts[0] == "apps" or parts[:2] == ("tests", "backend"):
        return True
    target = backend.joinpath(*parts)
    return target.exists() or (
        target.parent != backend and target.parent.is_dir() and bool(target.suffix)
    )


def resource_edges(
    tree: ast.AST,
    source: Path,
    owner: Path,
    backend: Path = HOST_BACKEND,
) -> Counter[str]:
    """Reject host-layout paths derived from source ancestors or the working directory.

    ``source`` and ``owner`` must be normalized the same way (both resolved).
    Paths below the owning SDK/plugin package stay allowed. Fragments appended
    to another path (``base / Path("prompts")``) are judged only as part of it;
    a relative literal is cwd-rooted only as the base of a complete expression.
    """
    edges: Counter[str] = Counter()
    nodes = list(ast.walk(tree))
    parents = {
        child: parent for parent in nodes for child in ast.iter_child_nodes(parent)
    }
    fragments = {id(part) for node in nodes for part in _fragments(node)}
    fragment_names = {
        node.id
        for node in nodes
        if isinstance(node, ast.Name) and id(node) in fragments
    }
    # String values are folded once in source order (as the import guard does);
    # conditional assignments keep every possible value.
    strings: dict[str, set[str]] = {}
    for name, value in _assignments(nodes):
        strings.setdefault(name, set()).update(literal_strings(value, strings))
    evaluator = _Evaluator(source, strings)
    # Source order first, so ``p = p / x`` and ``p /= x`` apply once to the
    # earlier value; then resolve other aliases (including names used before
    # their definition in function bodies) until stable.
    accumulated: set[str] = set()
    for name, value in _assignments(nodes):
        paths = evaluator.evaluate(value)
        if paths:
            evaluator.paths[name] = paths
        if _self_referential(name, value):
            accumulated.add(name)
    for _ in range(len(nodes)):
        changed = False
        for name, value in _assignments(nodes):
            if name in accumulated:
                continue
            paths = evaluator.evaluate(value)
            if paths and evaluator.paths.get(name) != paths:
                evaluator.paths[name] = paths
                changed = True
        if not changed:
            break

    def complete(node: ast.AST) -> bool:
        """The outermost path expression: its parent builds no further path."""
        parent = parents.get(node)
        if parent is None or evaluator.evaluate(parent):
            return False
        # SUB = Path("utils") is only a fragment when SUB is appended elsewhere.
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            targets = (
                parent.targets if isinstance(parent, ast.Assign) else [parent.target]
            )
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            return not names or not set(names) <= fragment_names
        return True

    for node in nodes:
        if id(node) in fragments:
            continue
        values = (
            evaluator.evaluate(node.target)
            if isinstance(node, ast.AugAssign)
            else evaluator.evaluate(node)
        )
        for value in values:
            if value.is_relative_to(_WORKING_DIRECTORY):
                relative = value.relative_to(_WORKING_DIRECTORY).as_posix()
            elif value.is_relative_to(_RELATIVE):
                if not complete(node):
                    continue
                relative = value.relative_to(_RELATIVE).as_posix()
            elif value.is_relative_to(_SENTINEL):
                continue  # Above the working directory: not a checkout layout.
            else:
                if not value.is_relative_to(owner):
                    edges["repository-layout path outside owning package"] += 1
                continue
            if host_layout(relative, backend):
                edges[f"repository resource via working directory: {relative}"] += 1
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parent = parents.get(node)
            # Documentation is not file access. Explicit fixture/runtime path
            # inputs (tmp_path / "...") are also independent of source layout;
            # path arguments are judged as paths above.
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
