"""What names mean in one module: import bindings and name assignments."""

import ast
from collections.abc import Iterator

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


def assignments(nodes: list[ast.AST]) -> Iterator[tuple[str, ast.expr]]:
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


class ModuleNames:
    """Resolves names and attribute chains to dotted origins (``os.path.join``)."""

    def __init__(self, nodes: list[ast.AST]) -> None:
        self.imports: dict[str, str] = {}
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self.imports[alias.asname] = alias.name
                    else:
                        root = alias.name.split(".")[0]
                        self.imports[root] = root
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for alias in node.names:
                    self.imports[alias.asname or alias.name] = (
                        f"{node.module}.{alias.name}"
                    )
        # Locally bound names never fall back to a module or builtin meaning.
        self.assigned = (
            {
                node.id
                for node in nodes
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
            }
            | {
                node.name
                for node in nodes
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
            }
            | {node.arg for node in nodes if isinstance(node, ast.arg)}
        )

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
