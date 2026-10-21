"""Host-only fixtures. Plugin tests load installed SDK support independently.

Default ``pytest`` collects the contract set in ``tests.support.default_suite``.
``pytest --also <path>`` keeps that set and also collects the given host paths.
``pytest --extended`` collects the rest of ``tests/backend``.
"""

from pathlib import Path

import pytest

from tests.support.default_suite import (
    REPO_ROOT,
    is_default_test,
    path_covered_by_also,
    selection_is_default_root,
    should_ignore_collect,
)
from tests.support.scheduler import (
    fixed_now,
    mock_loop,
    mock_push,
    service,
    store_path,
    tracker,
)
from tests.support.runtime_channels import runtime_channels


def pytest_addoption(parser: pytest.Parser) -> None:
    """Opt in to host tests outside the default CI selection."""
    parser.addoption(
        "--extended",
        action="store_true",
        default=False,
        help="Collect host tests outside the default CI selection (marker: extended).",
    )
    parser.addoption(
        "--also",
        action="append",
        default=[],
        help=(
            "Also collect these tests/backend paths without leaving the "
            "default allowlist. scripts/select_tests.py emits this."
        ),
    )


def _policy_active(config: pytest.Config) -> bool:
    if config.getoption("--extended"):
        return False
    args = [str(arg) for arg in config.args]
    return selection_is_default_root(args, cwd=Path.cwd(), root=REPO_ROOT)


def _also_paths(config: pytest.Config) -> tuple[str, ...]:
    raw = config.getoption("--also")
    if not raw:
        return ()
    found: list[str] = []
    cwd = Path.cwd()
    for arg in raw:
        path = Path(str(arg))
        if not path.is_absolute():
            path = cwd / path
        try:
            found.append(path.resolve().relative_to(REPO_ROOT).as_posix())
        except ValueError:
            continue
    return tuple(found)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    """Skip extended host tests unless the invocation asked for them."""
    if not _policy_active(config):
        return False
    try:
        relative = collection_path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return False
    if not relative.startswith("tests/backend"):
        return False
    if path_covered_by_also(relative, _also_paths(config)):
        return False
    return should_ignore_collect(relative, is_dir=collection_path.is_dir())


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Mark host tests that are outside the default selection."""
    marker = pytest.mark.extended
    for item in items:
        try:
            relative = Path(str(item.path)).resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            continue
        if relative.startswith("tests/backend/") and not is_default_test(relative):
            item.add_marker(marker)
