"""Constant folding of string expressions shared by the static SDK guards."""

import ast


def literal_strings(node: ast.AST, bindings: dict[str, set[str]]) -> set[str]:
    """Every value a string expression can take: literals, names, ``+``, f-strings.

    ``bindings`` maps names to their possible values; unknown parts yield no value.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name):
        return bindings.get(node.id, set())
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return {
            left + right
            for left in literal_strings(node.left, bindings)
            for right in literal_strings(node.right, bindings)
        }
    if isinstance(node, ast.JoinedStr):
        values = {""}
        for part in node.values:
            child = part.value if isinstance(part, ast.FormattedValue) else part
            values = {
                left + right
                for left in values
                for right in literal_strings(child, bindings)
            }
        return values
    return set()
