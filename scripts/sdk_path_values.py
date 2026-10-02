"""Lexical path values of expressions within one module.

Values come from ``__file__``, explicit working-directory anchors or relative
literals and are followed through names bound in the same module. Data flow
through attributes, containers, call results or loops (``self.root.parents[3]``,
``parents[-1]``, ``__spec__.origin``, ``sys.path[0]``, ``dirname`` in a loop) is
not modelled; external execution against installed wheels covers those.
"""

import ast
import os
from collections.abc import Iterator
from itertools import product
from pathlib import Path

from scripts.sdk_strings import literal_strings

# Lexical stand-ins for the unknown working directory and for paths relative to
# it. The padding keeps ``..`` escapes below the sentinel so they stay anchored.
_DEPTH = 16
_ROOT = Path(os.path.abspath(os.sep + "__shiori_layout__"))
WORKING_DIRECTORY = _ROOT.joinpath("cwd", *["_"] * _DEPTH)
RELATIVE = _ROOT.joinpath("relative", *["_"] * _DEPTH)

# Only concrete pathlib classes denote file-system paths; PurePath and friends
# are commonly used for archive members, URLs and keys.
CONCRETE_PATHS = frozenset({"pathlib.Path", "pathlib.PosixPath", "pathlib.WindowsPath"})
_PATHLIB_NAMES = frozenset(
    {
        "Path",
        "PosixPath",
        "WindowsPath",
        "PurePath",
        "PurePosixPath",
        "PureWindowsPath",
    }
)
# Unimported names resolved by convention: standard modules and builtins.
_MODULES = frozenset({"os", "ntpath", "pathlib", "glob", "shutil", "sys", "io"})
_BUILTINS = frozenset({"open", "str"})
_OS_PATH_MODULES = ("os.path", "ntpath")
_PATH_CONSTANTS = {"os.pardir": "..", "os.curdir": "."}


def anchored(value: Path) -> tuple[str, str] | None:
    """``("cwd" | "relative", layout)`` for stand-in values, None for real paths.

    Leading ``..`` escapes are dropped from ``layout``: ``../../apps/backend``
    still names ``apps/backend``.
    """
    if not value.is_relative_to(_ROOT):
        return None
    parts = list(value.relative_to(_ROOT).parts)
    if not parts:
        return "relative", ""
    kind, rest = parts[0], parts[1:]
    while rest and rest[0] == "_":
        rest.pop(0)
    return kind, "/".join(rest)


def expand_arguments(args: list[ast.expr]) -> list[ast.expr] | None:
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


def _imports(nodes: list[ast.AST]) -> dict[str, str]:
    bound: dict[str, str] = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bound[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    bound[root] = root
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                bound[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bound


class PathValues:
    """Possible path values of the expressions in one module."""

    def __init__(self, tree: ast.AST, source: Path) -> None:
        nodes = list(ast.walk(tree))
        self.source = source
        self.imports = _imports(nodes)
        self.assigned = {
            node.id
            for node in nodes
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        } | {node.arg for node in nodes if isinstance(node, ast.arg)}
        # String values are folded once in source order (as the import guard
        # does); conditional assignments keep every possible value.
        self.strings: dict[str, set[str]] = {}
        for name, value in _assignments(nodes):
            self.strings.setdefault(name, set()).update(
                literal_strings(value, self.strings)
            )
        self.paths: dict[str, set[Path]] = {}
        self._bind(nodes)

    def _bind(self, nodes: list[ast.AST]) -> None:
        # Source order first, so ``p = p / x`` and ``p /= x`` apply once to the
        # earlier value; then resolve other aliases (including names used before
        # their definition in function bodies) until stable.
        accumulated: set[str] = set()
        for name, value in _assignments(nodes):
            paths = self.evaluate(value)
            if paths:
                self.paths[name] = paths
            if any(
                isinstance(child, ast.Name) and child.id == name
                for child in ast.walk(value)
            ):
                accumulated.add(name)
        for _ in range(len(nodes)):
            changed = False
            for name, value in _assignments(nodes):
                if name in accumulated:
                    continue
                paths = self.evaluate(value)
                if paths and self.paths.get(name) != paths:
                    self.paths[name] = paths
                    changed = True
            if not changed:
                break

    def qualified(self, node: ast.AST) -> str | None:
        """Dotted origin of a name: import-bound, a standard module or a builtin."""
        if isinstance(node, ast.Name):
            if node.id in self.imports:
                return self.imports[node.id]
            if node.id in self.assigned:
                return None
            if node.id in _MODULES:
                return node.id
            if node.id in _PATHLIB_NAMES:
                return f"pathlib.{node.id}"
            if node.id in _BUILTINS:
                return f"builtins.{node.id}"
            return None
        if isinstance(node, ast.Attribute):
            base = self.qualified(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    def _os_path(self, node: ast.Call) -> str | None:
        """The function name of a genuine ``os.path``/``ntpath`` call."""
        qualified = self.qualified(node.func)
        if qualified:
            module, _, function = qualified.rpartition(".")
            if module in _OS_PATH_MODULES:
                return function
        return None

    def _texts(self, node: ast.expr) -> set[str]:
        """Relative component values: folded strings or relative path values."""
        constant = _PATH_CONSTANTS.get(self.qualified(node) or "")
        if constant:
            return {constant}
        values = literal_strings(node, self.strings)
        if values:
            return values
        paths = self.evaluate(node)
        if paths and all(path.is_relative_to(RELATIVE) for path in paths):
            return {path.relative_to(RELATIVE).as_posix() for path in paths}
        return set()

    def _join(self, bases: set[Path], values: list[set[str]]) -> set[Path]:
        if not all(values):
            return set()
        joined: set[Path] = set()
        for base, names in product(bases, product(*values)):
            if any(os.path.isabs(name) or Path(name).anchor for name in names):
                continue
            joined.add(Path(os.path.normpath(base.joinpath(*names))))
        return joined

    def join(self, bases: set[Path], parts: list[ast.expr]) -> set[Path]:
        """Joins relative components lexically; unknown components stop."""
        return self._join(bases, [self._texts(part) for part in parts])

    def argument(self, node: ast.expr) -> set[Path]:
        """A path argument: a derived path, or a relative literal."""
        return self.join({RELATIVE}, [node]) or self.evaluate(node)

    def _call(self, node: ast.Call) -> set[Path]:
        qualified = self.qualified(node.func)
        args = expand_arguments(node.args)
        if args is None:
            return set()
        if qualified in CONCRETE_PATHS:
            # Path() is the working directory; Path(a, "b") joins like os.path.join.
            if not args:
                return {WORKING_DIRECTORY}
            return self.join(self.argument(args[0]), args[1:])
        if not args and qualified in {
            *(f"{path}.cwd" for path in CONCRETE_PATHS),
            "os.getcwd",
        }:
            return {WORKING_DIRECTORY}
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in {"resolve", "absolute", "expanduser"}:
                return self.evaluate(node.func.value)
            if node.func.attr == "joinpath":
                return self.join(self.evaluate(node.func.value), args)
        if not args:
            return set()
        if qualified in {"builtins.str", "os.fspath"}:
            # Conversions keep a path's value; they never turn text into a path.
            return self.evaluate(args[0])
        function = self._os_path(node)
        if function in {"abspath", "realpath", "normpath"}:
            return self.argument(args[0])
        if function == "dirname":
            return {path.parent for path in self.argument(args[0])}
        if function == "join":
            return self.join(self.argument(args[0]), args[1:])
        return set()

    def _subscript(self, node: ast.Subscript) -> set[Path]:
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
            and self._os_path(node.value) == "split"
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
            return self._call(node)
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            return {path.parent for path in self.evaluate(node.value)}
        if isinstance(node, ast.Subscript):
            return self._subscript(node)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self.join(self.evaluate(node.left), [node.right])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            # os.getcwd() + "/apps/backend": a separator-led suffix is a child.
            bases = self.evaluate(node.left)
            suffixes = {
                text.lstrip("/\\")
                for text in literal_strings(node.right, self.strings)
                if text.startswith(("/", "\\"))
            }
            return self._join(bases, [suffixes]) if bases else set()
        return set()
