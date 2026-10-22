"""Report the plugin kernel's code lines against its budget (report only).

Counts lines holding code: blank lines, comments and docstrings are excluded
(docs/decisions/2026-10-22-plugin-system-four-layer-refactor.md §8.8). The
kernel ``shiori_sdk.kernel`` is created in P1; until then it reports 0 and the
current ``agent/plugin_host`` is printed as the baseline. The exit status is
always 0: the budget becomes a gate in P8.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = 700
KERNEL = ROOT / "packages/sdk/python/shiori_sdk/kernel"
BASELINE = ROOT / "apps/backend/agent/plugin_host"

_NON_CODE_TOKENS = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)


def _docstring_spans(tree: ast.AST) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Source spans of module, class and function docstrings."""
    spans: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            value = body[0].value
            end = (value.end_lineno or value.lineno, value.end_col_offset or 0)
            spans.append(((value.lineno, value.col_offset), end))
    return spans


def code_lines(source: str) -> int:
    """Lines with at least one code token outside comments and docstrings."""
    spans = _docstring_spans(ast.parse(source))
    lines: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in _NON_CODE_TOKENS:
            continue
        if any(start <= token.start and token.end <= end for start, end in spans):
            continue
        lines.update(range(token.start[0], token.end[0] + 1))
    return len(lines)


def tree_code_lines(folder: Path) -> tuple[int, int]:
    """(code lines, file count) of the Python sources below ``folder``."""
    files = [
        path for path in sorted(folder.rglob("*.py")) if "__pycache__" not in path.parts
    ]
    total = sum(code_lines(path.read_text(encoding="utf-8")) for path in files)
    return total, len(files)


def main() -> None:
    """Print the kernel count and the plugin_host baseline."""
    if KERNEL.is_dir():
        kernel, files = tree_code_lines(KERNEL)
        status = "within budget" if kernel <= BUDGET else "OVER BUDGET"
        print(
            f"shiori_sdk.kernel: {kernel} / {BUDGET} code lines ({files} files), {status}"
        )
    else:
        print(f"shiori_sdk.kernel: not created yet, 0 / {BUDGET} code lines")
    baseline, files = tree_code_lines(BASELINE)
    print(f"baseline agent/plugin_host: {baseline} code lines ({files} files)")


if __name__ == "__main__":
    main()
