"""String literals that spell repository paths, wherever they are used."""

import ast
from collections import Counter

from scripts.sdk_repository_layout import layout_literal


def layout_literals(
    nodes: list[ast.AST], parents: dict[ast.AST, ast.AST], judged: set[int]
) -> Counter[str]:
    """Counts literals starting with a repository directory.

    ``judged`` holds ids of nodes already reported by a path rule, so one
    violation is counted once. Documentation strings and explicit runtime path
    inputs (``tmp_path / "..."``) are not file access.
    """
    edges: Counter[str] = Counter()
    for node in nodes:
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        parent = parents.get(node)
        if id(node) in judged or isinstance(parent, ast.Expr):
            continue
        if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div):
            continue
        if layout_literal(node.value):
            edges[f"repository resource: {node.value}"] += 1
    return edges
