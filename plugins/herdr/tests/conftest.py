"""Shared isolated import generations for Herdr facades retaining one owner."""

import importlib
import importlib.util
import sys

import pytest

from shiori_sdk.testing.packages import plugin_directory


@pytest.fixture
def generations():
    """Import real plugin code twice, as independent runtime generations do."""
    directory = plugin_directory("herdr") / "backend"
    namespaces = ("herdr_test_retired", "herdr_test_current")
    modules = []
    try:
        for namespace in namespaces:
            spec = importlib.util.spec_from_file_location(
                namespace,
                directory / "__init__.py",
                submodule_search_locations=[str(directory)],
            )
            assert spec is not None and spec.loader is not None
            package = importlib.util.module_from_spec(spec)
            sys.modules[namespace] = package
            spec.loader.exec_module(package)
            modules.append(
                {
                    name: importlib.import_module(f"{namespace}.{name}")
                    for name in (
                        "cli",
                        "config",
                        "models",
                        "service",
                        "management_tools",
                        "dashboard",
                    )
                }
            )
        # Retirement removes old imports, while the process owner keeps its
        # service alive. No management operation may re-import that namespace.
        for name in tuple(sys.modules):
            if name == namespaces[0] or name.startswith(namespaces[0] + "."):
                del sys.modules[name]
        yield modules
    finally:
        for name in tuple(sys.modules):
            if any(
                name == prefix or name.startswith(prefix + ".") for prefix in namespaces
            ):
                del sys.modules[name]
