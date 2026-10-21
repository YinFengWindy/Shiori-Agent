"""Choose pytest paths from a diff against main.

The default allowlist in ``tests/support/default_suite.py`` always runs.
Changed paths add neighbor suites (memory and agent, desktop bridge and
agent, SDK and its own suite). Lockfiles, CI workflows, ``pytest.ini``,
the allowlist, this script, and any path the map does not recognize
widen to ``pytest --extended``.

Docs, the marketing site, and the Electron tree add nothing: a docs-only
diff stays on the allowlist. Plugin suites need their own environments,
so they run only in ``plugin-isolation``, which this map never turns off;
``verify_sdk`` stays unconditional as well.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_ESCALATE_EXACT = frozenset(
    {
        "pytest.ini",
        "pyproject.toml",
        "setup.py",
        "MANIFEST.in",
        "uv.lock",
        "pnpm-lock.yaml",
        "package-lock.json",
        "package.json",
        "pnpm-workspace.yaml",
        "pyrightconfig.json",
        "pyrightconfig.tests.json",
        "config.example.toml",
        "tests/conftest.py",
        "tests/backend/conftest.py",
        "scripts/select_tests.py",
    }
)
_ESCALATE_PREFIXES = (
    ".github/workflows/",
    "tests/support/",
    "apps/backend/requirements/",
)
_SKIP_PREFIXES = ("docs/", "apps/site/", "apps/desktop/", "assets/")
_SKIP_EXACT = frozenset(
    {
        "eslint.config.js",
        "vercel.json",
        "plugins/tsconfig.json",
        "LICENSE",
        "NOTICE",
    }
)
_DOC_SUFFIXES = (
    ".md",
    ".mdx",
    ".rst",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
)
# Longest prefixes first. A directory boundary is required so ``agent`` does
# not swallow an unrelated sibling name.
_BACKEND_HOST: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "apps/backend/core/memory",
        ("tests/backend/core/memory", "tests/backend/agent"),
    ),
    (
        "apps/backend/core/roles",
        (
            "tests/backend/core/roles",
            "tests/backend/agent",
            "tests/backend/core/memory",
        ),
    ),
    (
        "apps/backend/desktop_bridge",
        ("tests/backend/desktop_bridge", "tests/backend/agent"),
    ),
    (
        "apps/backend/agent",
        (
            "tests/backend/agent",
            "tests/backend/desktop_bridge",
            "tests/backend/core/memory",
        ),
    ),
    (
        "apps/backend/bootstrap",
        ("tests/backend/bootstrap", "tests/backend/agent"),
    ),
    ("apps/backend/session", ("tests/backend/session", "tests/backend/agent")),
    (
        "apps/backend/proactive_v2",
        ("tests/backend/proactive_v2", "tests/backend/agent"),
    ),
    ("apps/backend/bus", ("tests/backend/bus", "tests/backend/agent")),
    ("apps/backend/infra", ("tests/backend/infra", "tests/backend/agent")),
    (
        "apps/backend/conversation",
        ("tests/backend/conversation", "tests/backend/agent"),
    ),
    ("apps/backend/core", ("tests/backend/core", "tests/backend/agent")),
    ("apps/backend/main.py", ("tests/backend/bootstrap", "tests/backend/agent")),
)


class GitSelectionError(RuntimeError):
    """``git`` could not name the diff against main."""


@dataclass(frozen=True)
class Selection:
    """Pytest plan for one diff.

    ``default`` is the allowlist alone. ``selected`` adds ``host_paths``
    via ``pytest --also`` and ``external_paths`` in a second pytest process.
    ``extended`` is ``pytest --extended`` and already includes the allowlist.
    """

    mode: str
    host_paths: tuple[str, ...] = ()
    external_paths: tuple[str, ...] = ()


def normalize(path: str) -> str:
    """Return a repo-relative posix path without a leading ``./``."""
    text = path.replace("\\", "/").strip()
    if text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def select(paths: Iterable[str]) -> Selection:
    """Map changed paths to a pytest plan. Unknown inputs widen the plan."""
    host: list[str] = []
    external: list[str] = []
    for raw in paths:
        kind, mapped_host, mapped_external = _classify(normalize(raw))
        if kind == "skip":
            continue
        if kind == "escalate":
            return Selection("extended")
        host.extend(mapped_host)
        external.extend(mapped_external)
    if not host and not external:
        return Selection("default")
    return Selection("selected", _dedupe(host), _dedupe(external))


def materialize(selection: Selection, root: Path) -> Selection:
    """Widen when a chosen pytest path is not on disk. Never drop it."""
    if selection.mode == "extended":
        return selection
    for path in (*selection.host_paths, *selection.external_paths):
        if not (root / path).exists():
            return Selection("extended")
    if not selection.host_paths and not selection.external_paths:
        return Selection("default")
    return selection


def changed_paths(root: Path, *, base: str | None = None) -> list[str]:
    """Return paths changed since merge-base with main, or since ``base``."""
    ref = base or _merge_base(root)
    completed = subprocess.run(
        ["git", "diff", "--name-only", "-z", f"{ref}...HEAD"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise GitSelectionError(detail or f"git diff {ref}...HEAD failed")
    return [item for item in completed.stdout.decode().split("\0") if item]


def plan(
    root: Path | None = None,
    *,
    base: str | None = None,
) -> Selection:
    """Read ``git`` and return the pytest plan. Git failures widen."""
    repo = root or REPO_ROOT
    try:
        paths = changed_paths(repo, base=base)
    except GitSelectionError:
        return Selection("extended")
    return materialize(select(paths), repo)


def format_plan(selection: Selection) -> tuple[str, ...]:
    """Return ``mode=`` / ``also=`` / ``external=`` lines for the CI shell."""
    lines = [f"mode={selection.mode}"]
    if selection.mode == "extended":
        return tuple(lines)
    for path in selection.host_paths:
        lines.append(f"also={path}")
    for path in selection.external_paths:
        lines.append(f"external={path}")
    return tuple(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the plan for HEAD against ``--base`` (default: merge-base of main)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="Git ref to diff against. Default: merge-base of origin/main or main.",
    )
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        paths = changed_paths(args.root, base=args.base)
    except GitSelectionError as exc:
        print(f"select_tests: {exc}; widening to --extended", file=sys.stderr)
        selection = Selection("extended")
    else:
        selection = materialize(select(paths), args.root)
        if selection.mode == "extended":
            print("select_tests: widening to --extended", file=sys.stderr)
    for line in format_plan(selection):
        print(line)
    return 0


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(sorted(set(items)))


def _matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _merge_base(root: Path) -> str:
    for candidate in ("origin/main", "main"):
        verify = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if verify.returncode != 0:
            continue
        merge = subprocess.run(
            ["git", "merge-base", candidate, "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if merge.returncode != 0:
            continue
        sha = merge.stdout.decode().strip()
        if sha:
            return sha
    raise GitSelectionError("no merge-base against origin/main or main")


def _is_doc(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
        return True
    if path in _SKIP_EXACT:
        return True
    return path.endswith(_DOC_SUFFIXES)


def _classify(path: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if not path:
        return ("skip", (), ())
    if path in _ESCALATE_EXACT or any(
        path.startswith(prefix) for prefix in _ESCALATE_PREFIXES
    ):
        return ("escalate", (), ())
    if _is_doc(path):
        return ("skip", (), ())
    for prefix, hosts in _BACKEND_HOST:
        if _matches(path, prefix):
            return ("map", hosts, ())
    if _matches(path, "packages/sdk"):
        return (
            "map",
            ("tests/backend/agent/plugin_host", "tests/backend/scripts"),
            ("packages/sdk/tests",),
        )
    if _matches(path, "packages/shiori-host-testing"):
        return ("map", ("tests/backend/shiori_host_testing",), ())
    if path.startswith("plugins/"):
        plugin_id = path.split("/", 2)[1] if path.count("/") >= 1 else ""
        if not plugin_id or "." in plugin_id:
            return ("escalate", (), ())
        return ("map", ("tests/backend/agent/plugin_host",), ())
    if path.startswith("scripts/") and path.endswith((".py", ".pyi", ".mjs", ".mts")):
        return ("map", ("tests/backend/scripts",), ())
    if path.startswith("tests/backend/") and not path.endswith("/conftest.py"):
        name = path.rsplit("/", 1)[-1]
        if name.startswith("test_") and name.endswith(".py"):
            return ("map", (path,), ())
    return ("escalate", (), ())


if __name__ == "__main__":
    raise SystemExit(main())
