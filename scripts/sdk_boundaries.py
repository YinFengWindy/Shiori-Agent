"""Repository-owned host boundaries shared by static and installed-artifact checks."""

from pathlib import Path


def host_roots(repository: Path) -> frozenset[str]:
    """Discover importable backend roots, including future packages and entry modules."""
    backend = repository / "apps/backend"
    roots = {
        path.name if path.is_dir() else path.stem
        for path in backend.iterdir()
        if (path.is_dir() and any(path.rglob("*.py")))
        or (path.is_file() and path.suffix in {".py", ".pyi"})
    }
    return frozenset(roots) | {
        "memory2",  # Removed implementations must not return through old imports.
        "shiori_plugin_testkit",
        "shiori_host_testing",
        "tests",
    }
