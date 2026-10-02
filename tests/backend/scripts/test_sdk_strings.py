"""String folding yields every value a module-level string expression can take."""

import ast

from scripts.sdk_strings import literal_strings


def _value(expression: str, bindings: dict[str, set[str]]) -> set[str]:
    node = ast.parse(expression, mode="eval").body
    return literal_strings(node, bindings)


def test_concatenation_f_strings_and_bound_names_are_folded() -> None:
    bindings = {"root": {"agent", "core"}}
    assert _value("root + '.provider'", bindings) == {"agent.provider", "core.provider"}
    assert _value("f'{root}/x'", bindings) == {"agent/x", "core/x"}


def test_unknown_parts_yield_no_value() -> None:
    assert _value("unknown + '.provider'", {}) == set()
    assert _value("f'{call()}/x'", {}) == set()
