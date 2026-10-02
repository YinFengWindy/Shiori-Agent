"""Detect repository-layout resource access without rejecting plugin-owned files.

Three rules share one module evaluation (``scripts.sdk_path_values``):

* a complete path expression derived from ``__file__`` must stay inside the
  owning package, and one anchored at the working directory (``Path.cwd()``,
  ``os.getcwd()``, ``Path()``) must not name the host layout;
* a relative path reaching a file-system sink (``scripts.sdk_path_sinks``) must
  not name the host layout; other calls receive keys or plugin-relative names;
* literals starting with a repository directory are rejected anywhere
  (``scripts.sdk_layout_literals``).

The layout itself is defined in ``scripts.sdk_repository_layout``. A violation
is counted once, at the value where it first appears: paths derived from an
already violating path (``a = R / "a"``, ``p /= "x"``, a sink reading it) are the
same violation. Known limits are listed in sdk_path_values.
"""

import ast
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from scripts.sdk_layout_literals import layout_literals
from scripts.sdk_path_sinks import sink_paths
from scripts.sdk_path_values import PathValues, anchored
from scripts.sdk_repository_layout import HOST_BACKEND, host_layout, repository_prefix

# A rule maps one path value to its violation label, or None.
Rule = Callable[[Path], str | None]


def _expression_rule(owner: Path, backend: Path) -> Rule:
    """Complete expressions: source-derived, cwd-anchored and repository paths."""

    def violation(value: Path) -> str | None:
        anchor = anchored(value)
        if anchor is None:
            if value.is_relative_to(owner):
                return None
            return "repository-layout path outside owning package"
        kind, layout = anchor
        if kind == "cwd" and host_layout(layout, backend):
            return f"repository resource via working directory: {layout}"
        if kind == "relative" and repository_prefix(layout):
            return f"repository resource: {layout}"
        return None

    return violation


def _sink_rule(backend: Path) -> Rule:
    """Relative paths that a file-system operation resolves against the cwd."""

    def violation(value: Path) -> str | None:
        anchor = anchored(value)
        if anchor and anchor[0] == "relative" and host_layout(anchor[1], backend):
            return f"repository resource via file-system access: {anchor[1]}"
        return None

    return violation


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
    expression = _expression_rule(owner, backend)
    sink = _sink_rule(backend)
    edges: Counter[str] = Counter()
    origins: set[Path] = set()
    judged: set[int] = set()

    def judge(paths: set[Path], rule: Rule, node: ast.AST) -> None:
        for value in paths:
            label = rule(value)
            if label is None:
                continue
            judged.update(id(child) for child in ast.walk(node))
            origin = values.origin(
                value,
                lambda base: expression(base) is not None or sink(base) is not None,
            )
            if origin not in origins:
                origins.add(origin)
                edges[label] += 1

    # Source order, so a violation is reported where it is first written.
    for node in sorted(
        (node for node in nodes if hasattr(node, "lineno")),
        key=lambda node: (node.lineno, node.col_offset),
    ):
        if isinstance(node, ast.AugAssign):
            judge(values.evaluate(node.target), expression, node)
        # Names repeat a value judged where it was bound; nested parts of a
        # larger path expression are judged as that expression.
        elif (
            isinstance(node, ast.expr)
            and not isinstance(node, ast.Name)
            and node in parents
            and not values.evaluate(parents[node])
        ):
            judge(values.evaluate(node), expression, node)
        if isinstance(node, ast.Call):
            for path in sink_paths(node, values):
                judge(values.argument(path), sink, path)
    edges.update(layout_literals(nodes, parents, judged))
    return edges
