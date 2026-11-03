"""Enforce the SDK kernel's 700 code-line budget.

Blank lines, comments and docstrings are excluded (§8.8 of the four-layer
refactor decision). A missing or empty kernel is a failed gate, not zero LOC.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = 700
KERNEL = ROOT / "packages/sdk/python/shiori_sdk/kernel"

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


def main() -> int:
    """Report the kernel size and fail when sources are missing or over budget."""
    if not KERNEL.is_dir():
        print(f"shiori_sdk.kernel: missing source directory: {KERNEL}")
        return 1
    kernel, files = tree_code_lines(KERNEL)
    if not files:
        print(f"shiori_sdk.kernel: no Python sources in {KERNEL}")
        return 1
    status = "within budget" if kernel <= BUDGET else "OVER BUDGET"
    print(
        f"shiori_sdk.kernel: {kernel} / {BUDGET} code lines ({files} files), {status}"
    )
    return int(kernel > BUDGET)


if __name__ == "__main__":
    raise SystemExit(main())
