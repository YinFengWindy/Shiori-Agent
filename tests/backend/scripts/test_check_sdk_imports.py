"""Negative coverage for the SDK boundary, including typing and baseline regressions."""

from pathlib import Path

import pytest

from scripts.check_sdk_imports import host_imports, ratchet, scan, violations


def test_guard_rejects_runtime_function_typing_and_dynamic_host_imports() -> None:
    imports = host_imports(
        "from core.roles.store import RoleStore\n"
        "if TYPE_CHECKING:\n    from agent.plugin_host.runtime_context import PluginRuntimeContext\n"
        "def load():\n    import conversation.context_scope\n"
        "import importlib\n"
        "importlib.import_module('infra.channels')\n"
        "__import__('bootstrap')\n"
        "from shiori_sdk import PluginRuntimeContext\n"
    )
    assert set(imports) == {
        "core.roles.store.RoleStore",
        "agent.plugin_host.runtime_context.PluginRuntimeContext",
        "conversation.context_scope",
        "infra.channels",
        "bootstrap",
    }
    assert len(violations({"plugins/demo/backend/plugin.py": dict(imports)}, {})) == 5


@pytest.mark.parametrize(
    "source",
    [
        "from importlib import import_module\nimport_module('agent.plugin_host.kernel')",
        "from importlib import import_module as load\nload('agent.plugin_host.kernel')",
        "import importlib as loader\nloader.import_module(name='agent.plugin_host.kernel')",
        "from builtins import __import__ as load\nload('agent.plugin_host.kernel')",
        "import builtins as runtime\nruntime.__import__('agent.plugin_host.kernel')",
        "load = __import__\nload('agent.plugin_host.kernel')",
        "from importlib import import_module\nload = import_module\nalias = load\nalias('agent.plugin_host.kernel')",
        "def setup():\n    load('agent.plugin_host.kernel')\nfrom importlib import import_module as load",
        "def setup():\n    from importlib import import_module as load\n    load('agent.plugin_host.kernel')",
    ],
)
def test_guard_rejects_imported_and_assigned_dynamic_import_aliases(
    source: str,
) -> None:
    imports = host_imports(source)
    assert imports == {"agent.plugin_host.kernel": 1}
    assert violations({"plugins/demo/backend/plugin.py": dict(imports)}, {})


def test_dynamic_import_aliases_do_not_leak_or_match_unrelated_callables() -> None:
    assert (
        host_imports(
            "def first():\n    from importlib import import_module as load\n"
            "def second(load):\n    load('agent.fake')\n"
            "def third(service):\n    service.import_module('agent.fake')\n"
        )
        == {}
    )


def test_scan_includes_sdk_plugin_tests_and_packaged_support(tmp_path: Path) -> None:
    paths = [
        "packages/sdk/python/shiori_sdk/example.py",
        "packages/sdk/python/shiori_sdk/stub.pyi",
        "plugins/demo/backend/plugin.py",
        "plugins/demo/tests/test_plugin.py",
        "plugins/demo/testing/http.py",
        "plugins/demo/testing/stub.pyi",
    ]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("from bus.event_bus import EventBus\n", encoding="utf-8")
    assert set(scan(tmp_path)) == set(paths)


def test_baseline_cannot_add_edges_or_counts_but_can_shrink() -> None:
    previous = {"plugins/legacy/backend/plugin.py": {"agent.tools.Tool": 2}}
    assert (
        ratchet({"plugins/legacy/backend/plugin.py": {"agent.tools.Tool": 1}}, previous)
        == []
    )
    assert ratchet(
        {"plugins/legacy/backend/plugin.py": {"agent.tools.Tool": 3}}, previous
    )
    assert ratchet(
        {"plugins/legacy/backend/plugin.py": {"core.store.Store": 1}}, previous
    )
    assert ratchet({"plugins/new/backend/plugin.py": {"agent.tools.Tool": 1}}, previous)
    assert violations({}, previous)  # Removed imports must remove their exemption.
