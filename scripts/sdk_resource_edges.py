"""Detect repository-layout resource access without rejecting plugin-owned files.

Three rules share one module evaluation (``scripts.sdk_path_values``):

* a complete path expression derived from ``__file__`` must stay inside the
  owning package, and one anchored at the working directory (``Path.cwd()``,
  ``os.getcwd()``, ``Path()``) must not name the host layout;
* a relative path reaching a file-system sink (``scripts.sdk_path_sinks``) must
  not name the host layout; other calls receive keys or plugin-relative names;
* literals spelling repository directories are rejected anywhere
  (``scripts.sdk_layout_literals``).

Each violation is counted once. Known limits are listed in sdk_path_values.
"""

import ast
from collections import Counter
from pathlib import Path

from scripts.sdk_layout_literals import layout_literals
from scripts.sdk_path_sinks import (
    HOST_BACKEND,
    host_layout,
    repository_prefix,
    sink_paths,
)
from scripts.sdk_path_values import PathValues, anchored


def _expression_violations(values: set[Path], owner: Path, backend: Path) -> set[str]:
    """Violations of one complete path expression, whatever it was derived from."""
    labels: set[str] = set()
    for value in values:
        anchor = anchored(value)
        if anchor is None:
            if not value.is_relative_to(owner):
                labels.add("repository-layout path outside owning package")
            continue
        kind, layout = anchor
        if kind == "cwd" and host_layout(layout, backend):
            labels.add(f"repository resource via working directory: {layout}")
        elif kind == "relative" and repository_prefix(layout):
            labels.add(f"repository resource: {layout}")
    return labels


def _sink_violations(values: set[Path], backend: Path) -> set[str]:
    """Relative paths that a file-system operation resolves against the cwd."""
    labels: set[str] = set()
    for value in values:
        anchor = anchored(value)
        if anchor and anchor[0] == "relative" and host_layout(anchor[1], backend):
            labels.add(f"repository resource via file-system access: {anchor[1]}")
    return labels


def resource_edges(
    tree: ast.AST,
    source: Path,
    owner: Path,
    backend: Path = HOST_BACKEND,
) -> Counter[str]:
    """Reject host-layout paths derived from source ancestors or the working directory.

    ``source`` and ``owner`` must be normalized the same way (both resolved).
    Paths below the owning SDK/plugin package stay allowed.
    """
    values = PathValues(tree, source)
    nodes = list(ast.walk(tree))
    parents = {
        child: parent for parent in nodes for child in ast.iter_child_nodes(parent)
    }
    edges: Counter[str] = Counter()
    judged: set[int] = set()

    def report(labels: set[str], node: ast.AST) -> None:
        edges.update(labels)
        if labels:
            judged.update(id(child) for child in ast.walk(node))

    for node in nodes:
        if isinstance(node, ast.AugAssign):
            report(
                _expression_violations(values.evaluate(node.target), owner, backend),
                node,
            )
        # Names repeat a value judged where it was bound; nested parts of a
        # larger path expression are judged as that expression.
        elif (
            isinstance(node, ast.expr)
            and not isinstance(node, ast.Name)
            and node in parents
            and not values.evaluate(parents[node])
        ):
            report(_expression_violations(values.evaluate(node), owner, backend), node)
        if isinstance(node, ast.Call):
            for path in sink_paths(node, values):
                report(_sink_violations(values.argument(path), backend), path)
    edges.update(layout_literals(nodes, parents, judged))
    return edges
