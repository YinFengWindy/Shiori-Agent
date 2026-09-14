"""Static entry artifact checks; these never evaluate Python or JavaScript."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_paths import contained_file

# Lexical format checks deliberately do not claim to be a JavaScript parser.
_JS_TOKENS = re.compile(
    r"(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)"
    r"|(?P<string>'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)"
    r"|(?P<word>[A-Za-z_$][\w$]*)|(?P<punct>[^\s])"
)


def validate_artifact(root: Path, value: object, field: str, suffix: str) -> str:
    """Check containment, required artifact extension, encoding and entry shape.

    Python is parsed without compilation/execution. ESM gets lexical default
    export/CommonJS checks; the renderer loader owns full JS parsing and exports.
    """
    path = contained_file(root, value, field)
    if path.suffix != suffix:
        raise PackageContractError(
            "unsupported_format", field, f"Expected {suffix} artifact", path=str(value)
        )
    try:
        text = path.read_text(encoding="utf-8")
        if suffix == ".py":
            _backend(text, str(value), field)
        elif suffix == ".mjs":
            tokens = [
                match[0] if match.lastgroup != "string" else None
                for match in _JS_TOKENS.finditer(text)
                if match.lastgroup != "comment"
            ]
            direct_default = any(
                left == "export" and right == "default"
                for left, right in zip(tokens, tokens[1:])
            )
            # Bundlers commonly emit `export { generated_name as default }`.
            named_default = _has_named_default(tokens)
            if not (direct_default or named_default):
                raise PackageContractError(
                    "unsupported_format",
                    field,
                    "ESM entry requires export default",
                    path=str(value),
                )
            if any(
                tokens[index : index + 3] == ["module", ".", "exports"]
                for index in range(len(tokens))
            ) or any(
                left == "require" and right == "("
                for left, right in zip(tokens, tokens[1:])
            ):
                raise PackageContractError(
                    "unsupported_format",
                    field,
                    "CommonJS is unsupported; emit ESM",
                    path=str(value),
                )
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise PackageContractError(
            "invalid_entry", field, str(exc), path=str(value)
        ) from exc
    return str(value)


def _has_named_default(tokens: list[str | None]) -> bool:
    for index in range(len(tokens) - 1):
        if tokens[index : index + 2] != ["export", "{"]:
            continue
        end = index + 2
        while end < len(tokens) and tokens[end] not in {"}", ";"}:
            end += 1
        if end == len(tokens) or tokens[end] != "}":
            continue
        for start in range(index + 2, end - 2):
            # A literal remains an opaque token, so its contents cannot become
            # syntax or make separated identifiers appear adjacent.
            name = tokens[start]
            if (
                tokens[start - 1] in {"{", ","}
                and name is not None
                and re.fullmatch(r"[A-Za-z_$][\w$]*", name)
                and tokens[start + 1 : start + 3] == ["as", "default"]
                and tokens[start + 3] in {",", "}"}
            ):
                return True
    return False


def _backend(text: str, path: str, field: str) -> None:
    tree = ast.parse(text, filename=path)
    setup = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "setup"
        ),
        None,
    )
    if setup is None:
        raise PackageContractError(
            "invalid_entry", field, "Backend must declare async setup(ctx)", path=path
        )
    positional = len(setup.args.posonlyargs) + len(setup.args.args)
    required = positional - len(setup.args.defaults)
    if (
        required > 1
        or (positional < 1 and setup.args.vararg is None)
        or any(default is None for default in setup.args.kw_defaults)
    ):
        raise PackageContractError(
            "invalid_entry",
            field,
            "Backend setup must accept one positional context without other required arguments",
            path=path,
        )
