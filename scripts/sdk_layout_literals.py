"""String literals that spell repository paths, wherever they are used."""

import ast
from collections import Counter

LAYOUT_FRAGMENTS = ("apps/backend/", "tests/backend/", "apps/desktop/")


def layout_literals(
    nodes: list[ast.AST], parents: dict[ast.AST, ast.AST], judged: set[int]
) -> Counter[str]:
    """Counts literals naming repository directories.

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
        normalized = node.value.replace("\\", "/")
        if any(fragment in normalized for fragment in LAYOUT_FRAGMENTS):
            edges[f"repository resource: {node.value}"] += 1
    return edges
