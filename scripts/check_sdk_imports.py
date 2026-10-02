"""Reject host dependencies in every SDK/plugin source, stub and test support file."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from scripts.sdk_boundaries import host_roots
from scripts.sdk_resource_edges import resource_edges

ROOT = Path(__file__).resolve().parents[1]
HOST_ROOTS = host_roots(ROOT)


def _scope_nodes(node: ast.AST):
    """Walks one lexical scope, leaving nested scopes for a separate pass."""
    for child in ast.iter_child_nodes(node):
        yield child
        if not isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            yield from _scope_nodes(child)


def _identities(node: ast.AST, bindings: dict[str, set[str]]) -> set[str]:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, set())
    if isinstance(node, ast.Attribute):
        return {
            f"{name}.{node.attr}"
            for name in _identities(node.value, bindings)
            if name
            in {
                "importlib",
                "importlib.resources",
                "builtins",
                "unittest",
                "unittest.mock",
                "unittest.mock.patch",
            }
        }
    return set()


def _scope_imports(
    scope: ast.AST,
    inherited: dict[str, set[str]],
    edges: Counter[str],
    forbidden: frozenset[str],
    inherited_strings: dict[str, set[str]],
) -> None:
    nodes = list(_scope_nodes(scope))
    bindings = {name: set(values) for name, values in inherited.items()}
    strings = {name: set(values) for name, values in inherited_strings.items()}
    # Local bindings shadow outer aliases. Within a scope, retain every possible
    # imported identity so conditional assignments cannot conceal a host import.
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bindings.pop(node.id, None)
            strings.pop(node.id, None)
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        for arg in ast.walk(scope.args):
            if isinstance(arg, ast.arg):
                bindings.pop(arg.arg, None)
                strings.pop(arg.arg, None)
    for node in nodes:
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                identity = alias.name if alias.asname else local
                bindings.setdefault(local, set()).add(identity)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [f"{node.module}.{alias.name}" for alias in node.names]
            for alias in node.names:
                bindings.setdefault(alias.asname or alias.name, set()).add(
                    f"{node.module}.{alias.name}"
                )
        for name in names:
            if name.split(".")[0] in forbidden:
                edges[name] += 1

    # Follow simple callable aliases (load = import_module, including alias chains).
    changed = True
    for _ in range(len(nodes)):
        if not changed:
            break
        changed = False
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                for target in targets:
                    if isinstance(target, ast.Name):
                        identities = _identities(node.value, bindings)
                        previous = bindings.setdefault(target.id, set())
                        changed |= not identities <= previous
                        previous.update(identities)
    # String assignments are evaluated once in source order. Re-evaluating
    # `name = name + suffix` in the alias fixed point grows values forever.
    # Retain possible earlier values for conditional assignments conservatively.
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            values = _strings(node.value, strings)
            for target in targets:
                if isinstance(target, ast.Name):
                    strings.setdefault(target.id, set()).update(values)
    for node in nodes:
        if isinstance(node, ast.Call):
            identities = _identities(node.func, bindings)
            dynamic = bool(
                identities
                & {
                    "importlib.import_module",
                    "builtins.__import__",
                    "unittest.mock.patch",
                    "unittest.mock.patch.multiple",
                    "importlib.resources.files",
                    "importlib.resources.read_text",
                    "importlib.resources.read_binary",
                    "importlib.resources.open_text",
                    "importlib.resources.open_binary",
                    "pkgutil.get_data",
                }
            )
            # pytest's monkeypatch is a fixture rather than an imported function;
            # a dotted string target still names a concrete import dependency.
            patch = isinstance(node.func, ast.Attribute) and node.func.attr in {
                "setattr",
                "delattr",
                "setitem",
            }
            if dynamic or patch:
                arguments = node.args[:1] or [
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg in {"name", "target", "package", "anchor"}
                ]
                for argument in arguments:
                    for name in _strings(argument, strings):
                        if name.split(".")[0] in forbidden:
                            edges[name] += 1
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            _scope_imports(node, bindings, edges, forbidden, strings)


def _strings(node: ast.AST, bindings: dict[str, set[str]]) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name):
        return bindings.get(node.id, set())
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return {
            left + right
            for left in _strings(node.left, bindings)
            for right in _strings(node.right, bindings)
        }
    if isinstance(node, ast.JoinedStr):
        values = {""}
        for part in node.values:
            child = part.value if isinstance(part, ast.FormattedValue) else part
            values = {
                left + right for left in values for right in _strings(child, bindings)
            }
        return values
    return set()


def host_imports(source: str, forbidden: frozenset[str] = HOST_ROOTS) -> Counter[str]:
    """Counts host edges, including typed imports and aliased dynamic import calls."""
    edges: Counter[str] = Counter()
    _scope_imports(
        ast.parse(source), {"__import__": {"builtins.__import__"}}, edges, forbidden, {}
    )
    return edges


def scan(root: Path) -> dict[str, dict[str, int]]:
    """Scans SDK and plugin sources, tests and packaged test support, never builds."""
    folders = [root / "packages/sdk/python", root / "packages/sdk/tests"]
    # Include arbitrary packaged support directories as well as backend/tests:
    # moving an import into a new Python package must not evade the guard.
    folders.extend(plugin for plugin in (root / "plugins").iterdir() if plugin.is_dir())
    found: dict[str, dict[str, int]] = {}
    for folder in folders:
        for path in sorted((*folder.rglob("*.py"), *folder.rglob("*.pyi"))):
            if any(part in {".venv", "build", "__pycache__"} for part in path.parts):
                continue
            source = path.read_text(encoding="utf-8")
            sdk = path.is_relative_to(root / "packages/sdk")
            forbidden = HOST_ROOTS | {"plugins"} if sdk else HOST_ROOTS
            imports = host_imports(source, forbidden)
            owner = (
                root / "packages/sdk"
                if sdk
                else root / "plugins" / path.relative_to(root / "plugins").parts[0]
            )
            imports.update(
                resource_edges(ast.parse(source), path.resolve(), owner.resolve())
            )
            if imports:
                found[path.relative_to(root).as_posix()] = dict(sorted(imports.items()))
    return dict(sorted(found.items()))


def dependency_violations(root: Path) -> list[str]:
    """Forbid host requirements in every extra and concrete plugin requirements in SDK."""
    errors = []
    for path in (
        root / "packages/sdk/pyproject.toml",
        *(root / "plugins").glob("*/pyproject.toml"),
    ):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        requirements = list(project.get("dependencies", []))
        for extra in project.get("optional-dependencies", {}).values():
            requirements.extend(extra)
        for requirement in requirements:
            name = canonicalize_name(Requirement(requirement).name)
            if name in {
                "shiori-agent",
                "shiori-host-testing",
                "shiori-plugin-testkit",
            } or (
                path.is_relative_to(root / "packages/sdk")
                and name.startswith("shiori-plugin-")
            ):
                errors.append(
                    f"{path.relative_to(root).as_posix()}: forbidden dependency {requirement}"
                )
    return errors


def violations(actual: dict[str, dict[str, int]]) -> list[str]:
    """Return every forbidden edge; there is no allowlist or migration override."""
    return sorted(
        f"{path}: {name}: {count} forbidden reference(s)"
        for path, imports in actual.items()
        for name, count in imports.items()
    )


def main() -> None:
    """Check all SDK and plugin boundaries without migration exemptions."""
    errors = violations(scan(ROOT)) + dependency_violations(ROOT)
    if errors:
        raise SystemExit("\n".join(errors))
    print("SDK/plugin boundary passed (zero forbidden references, no exemptions)")


if __name__ == "__main__":
    main()
