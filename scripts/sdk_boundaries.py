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


# Distribution names. Every ``shiori-*`` distribution is built locally from this
# repository; none of them may be resolved from a package index.
LOCAL_DISTRIBUTION_PREFIX = "shiori-"
PLUGIN_DISTRIBUTION_PREFIX = "shiori-plugin-"
HOST_DISTRIBUTIONS = frozenset(
    {"shiori-agent", "shiori-host-testing", "shiori-plugin-testkit"}
)


def is_local_distribution(name: str) -> bool:
    """Whether a (canonical) distribution name belongs to this repository."""
    return name.startswith(LOCAL_DISTRIBUTION_PREFIX)


def plugin_distribution(plugin_id: str) -> str:
    """Distribution name of the plugin package in ``plugins/<plugin_id>``."""
    return PLUGIN_DISTRIBUTION_PREFIX + plugin_id.replace("_", "-")


def plugin_id_of(distribution: str) -> str | None:
    """Plugin directory of a (canonical) plugin distribution; None otherwise."""
    if distribution in HOST_DISTRIBUTIONS or not distribution.startswith(
        PLUGIN_DISTRIBUTION_PREFIX
    ):
        return None
    return distribution.removeprefix(PLUGIN_DISTRIBUTION_PREFIX).replace("-", "_")
