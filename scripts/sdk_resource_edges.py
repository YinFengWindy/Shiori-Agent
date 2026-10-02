"""Detect repository-layout resource access without rejecting plugin-owned files."""

import ast
import os
import re
from collections import Counter
from pathlib import Path

# Lexical stand-in for the process working directory. Paths derived from it are
# judged by their relative layout, because the working directory is unknown.
_WORKING_DIRECTORY = Path(os.path.abspath(os.sep + "__shiori_working_directory__"))
_HOST_LAYOUT = re.compile(r"(?:^|/)(?:apps/backend|apps/desktop|tests/backend)(?:/|$)")
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


def _join(base: Path | None, parts: list[ast.expr]) -> Path | None:
    """Joins constant relative components lexically; anything else is unknown."""
    if base is None:
        return None
    names: list[str] = []
    for part in parts:
        if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
            return None
        if os.path.isabs(part.value) or Path(part.value).anchor:
            return None
        names.append(part.value)
    return Path(os.path.normpath(base.joinpath(*names)))


def _base(node: ast.expr, bindings: dict[str, Path], source: Path) -> Path | None:
    """A path argument: a derived path, or a relative string (working directory)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _join(_WORKING_DIRECTORY, [node])
    return _path(node, bindings, source)


def _call_path(node: ast.Call, bindings: dict[str, Path], source: Path) -> Path | None:
    name = _callee(node)
    args = node.args
    if name in _PATH_TYPES:
        # Path() is the working directory; Path(a, "b") joins like os.path.join.
        if not args:
            return _WORKING_DIRECTORY
        return _join(_base(args[0], bindings, source), args[1:])
    if name in {"cwd", "getcwd"} and not args:
        return _WORKING_DIRECTORY
    if isinstance(node.func, ast.Attribute) and name in {
        "resolve",
        "absolute",
        "expanduser",
    }:
        return _path(node.func.value, bindings, source)
    if isinstance(node.func, ast.Attribute) and name == "joinpath":
        return _join(_path(node.func.value, bindings, source), args)
    if not args:
        return None
    if name in {"abspath", "realpath", "normpath", "str", "fspath"}:
        return _base(args[0], bindings, source)
    if name == "dirname":
        base = _base(args[0], bindings, source)
        return base.parent if base else None
    # os.path.join(...), but never str.join on a literal separator.
    if name == "join" and not (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Constant)
    ):
        return _join(_base(args[0], bindings, source), args[1:])
    return None


def _path(node: ast.AST, bindings: dict[str, Path], source: Path) -> Path | None:
    if isinstance(node, ast.Name):
        return source if node.id == "__file__" else bindings.get(node.id)
    if isinstance(node, ast.Call):
        return _call_path(node, bindings, source)
    if isinstance(node, ast.Attribute) and node.attr == "parent":
        base = _path(node.value, bindings, source)
        return base.parent if base else None
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, int)
    ):
        base = _path(node.value.value, bindings, source)
        if base and 0 <= node.slice.value < len(base.parents):
            return base.parents[node.slice.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _join(_path(node.left, bindings, source), [node.right])
    return None


def resource_edges(tree: ast.AST, source: Path, owner: Path) -> Counter[str]:
    """Reject host-layout paths derived from source ancestors or the working directory.

    ``source`` and ``owner`` must be normalized the same way (both resolved).
    Paths below the owning SDK/plugin package stay allowed.
    """
    bindings: dict[str, Path] = {}
    edges: Counter[str] = Counter()
    nodes = list(ast.walk(tree))
    parents = {
        child: parent for parent in nodes for child in ast.iter_child_nodes(parent)
    }
    # Resolve simple path aliases until stable, including aliases used earlier in
    # function bodies. This is a lint check, not a sandbox for arbitrary Python.
    for _ in range(len(nodes)):
        changed = False
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                value = _path(node.value, bindings, source)
                for target in targets:
                    if (
                        isinstance(target, ast.Name)
                        and value
                        and bindings.get(target.id) != value
                    ):
                        bindings[target.id] = value
                        changed = True
        if not changed:
            break
    for node in nodes:
        value = _path(node, bindings, source)
        if value is None:
            pass
        elif value.is_relative_to(_WORKING_DIRECTORY):
            # Path.cwd() / "apps/backend" assumes the process runs in a checkout.
            relative = value.relative_to(_WORKING_DIRECTORY).as_posix()
            if _HOST_LAYOUT.search(relative):
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
