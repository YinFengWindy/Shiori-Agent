"""Reject host imports in SDK/plugins, with a strictly shrinking migration baseline."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "scripts/sdk_import_exemptions.json"
# All installed host roots from setup.py, plus host tests and the legacy testkit.
HOST_ROOTS = frozenset(
    {
        "agent",
        "bootstrap",
        "bus",
        "conversation",
        "core",
        "desktop_bridge",
        "infra",
        "memory2",
        "proactive_v2",
        "prompts",
        "session",
        "utils",
        "shiori_runtime_resources",
        "shiori_host_testing",
        "tests",
        "shiori_plugin_testkit",
    }
)


def host_imports(source: str) -> Counter[str]:
    """Counts host edges even inside functions and TYPE_CHECKING branches."""
    edges: Counter[str] = Counter()
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [f"{node.module}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Call) and node.args:
            call = node.func
            dynamic = (isinstance(call, ast.Name) and call.id == "__import__") or (
                isinstance(call, ast.Attribute) and call.attr == "import_module"
            )
            if dynamic and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str):
                    names = [value]
        for name in names:
            if name.split(".")[0] in HOST_ROOTS:
                edges[name] += 1
    return edges


def scan(root: Path) -> dict[str, dict[str, int]]:
    """Scans only SDK sources/tests and each plugin's backend/tests, never builds."""
    folders = [root / "packages/sdk/python", root / "packages/sdk/tests"]
    folders.extend(
        area
        for plugin in (root / "plugins").iterdir()
        if plugin.is_dir()
        for area in (plugin / "backend", plugin / "tests")
    )
    found: dict[str, dict[str, int]] = {}
    for folder in folders:
        for path in sorted((*folder.rglob("*.py"), *folder.rglob("*.pyi"))):
            if any(part in {".venv", "build", "__pycache__"} for part in path.parts):
                continue
            imports = host_imports(path.read_text(encoding="utf-8"))
            if imports:
                found[path.relative_to(root).as_posix()] = dict(sorted(imports.items()))
    return dict(sorted(found.items()))


def violations(
    actual: dict[str, dict[str, int]], allowed: dict[str, dict[str, int]]
) -> list[str]:
    """Lists new or increased edges; unused exemptions must also be removed."""
    errors = []
    for path in actual.keys() | allowed.keys():
        current, previous = actual.get(path, {}), allowed.get(path, {})
        for name in current.keys() | previous.keys():
            count, limit = current.get(name, 0), previous.get(name, 0)
            if count != limit:
                errors.append(f"{path}: {name}: found {count}, exemption {limit}")
    return sorted(errors)


def ratchet(
    current: dict[str, dict[str, int]], previous: dict[str, dict[str, int]]
) -> list[str]:
    """Rejects baseline edits that add files, import edges or occurrences."""
    return sorted(
        f"{path}: exemption increased for {name}"
        for path, imports in current.items()
        for name, count in imports.items()
        if count > previous.get(path, {}).get(name, 0)
    )


def main() -> None:
    """Checks source edges and optionally verifies monotonicity against a Git base."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", help="Pinned PR base SHA; exemptions may only decrease"
    )
    args = parser.parse_args()
    allowed = json.loads((ROOT / BASELINE).read_text(encoding="utf-8"))
    errors = violations(scan(ROOT), allowed)
    # SDK and graduated plugins can never be re-added, even during bootstrap.
    for path in allowed:
        if not path.startswith("plugins/") or path.split("/")[1] in {
            "citation",
            "context_pressure",
        }:
            errors.append(f"{path}: migrated code cannot have import exemptions")
    if args.base:
        result = subprocess.run(
            ["git", "show", f"{args.base}:{BASELINE}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode == 0:
            errors.extend(ratchet(allowed, json.loads(result.stdout)))
        else:
            # Only the foundation PR can introduce this baseline. A missing ref is
            # an error; an existing base without the new file is its bootstrap.
            subprocess.run(
                ["git", "cat-file", "-e", f"{args.base}^{{commit}}"],
                cwd=ROOT,
                check=True,
            )
            print("Introducing the SDK migration baseline on an existing base commit")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"SDK import boundary passed ({sum(map(len, allowed.values()))} remaining legacy edges)"
    )


if __name__ == "__main__":
    main()
