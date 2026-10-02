"""Detect repository-layout resource access without rejecting plugin-owned files."""

import ast
from collections import Counter
from pathlib import Path


def _path(node: ast.AST, bindings: dict[str, Path], source: Path) -> Path | None:
    if isinstance(node, ast.Name):
        return source if node.id == "__file__" else bindings.get(node.id)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "Path" and node.args:
            return _path(node.args[0], bindings, source)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "resolve",
            "absolute",
        }:
            return _path(node.func.value, bindings, source)
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
        base = _path(node.left, bindings, source)
        if (
            base
            and isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, str)
        ):
            return (base / node.right.value).resolve()
    return None


def resource_edges(tree: ast.AST, source: Path, owner: Path) -> Counter[str]:
    """Reject paths derived from source ancestors outside the owning SDK/plugin package."""
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
        if value and not value.is_relative_to(owner):
            edges["repository-layout path outside owning package"] += 1
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            parent = parents.get(node)
            # Documentation is not file access. Explicit fixture/runtime path
            # inputs (tmp_path / "...") are also independent of source layout.
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
