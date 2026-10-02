"""Negative coverage for the SDK boundary, including typing and indirect references."""

from pathlib import Path

import pytest

from scripts.check_sdk_imports import (
    HOST_ROOTS,
    dependency_violations,
    host_imports,
    scan,
    violations,
)


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
    assert len(violations({"plugins/demo/backend/plugin.py": dict(imports)})) == 5


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
    assert violations({"plugins/demo/backend/plugin.py": dict(imports)})


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
        "plugins/demo/new_packaged_support/stub.pyi",
    ]
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("from bus.event_bus import EventBus\n", encoding="utf-8")
    assert set(scan(tmp_path)) == set(paths)


def test_scan_reports_violations_when_the_checkout_is_below_a_build_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "build" / ".venv" / "checkout"
    plugin = root / "plugins/demo/backend/plugin.py"
    plugin.parent.mkdir(parents=True)
    (root / "packages/sdk/python").mkdir(parents=True)
    (root / "packages/sdk/tests").mkdir(parents=True)
    plugin.write_text("from bus.event_bus import EventBus\n", encoding="utf-8")
    assert set(scan(root)) == {"plugins/demo/backend/plugin.py"}


def test_scan_includes_package_internal_build_directories_but_not_build_outputs(
    tmp_path: Path,
) -> None:
    scanned = [
        "plugins/demo/backend/build/helper.py",
        "plugins/demo/testing/dist/stub.pyi",
    ]
    skipped = [
        # setuptools output next to pyproject.toml, not the importable package.
        "plugins/demo/build/lib/plugins/demo/backend/plugin.py",
        "plugins/demo/dist/plugin.py",
        "plugins/demo/.venv/Lib/site-packages/host.py",
        "plugins/demo/environment/Lib/site-packages/host.py",
    ]
    for name in (*scanned, *skipped):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("from bus.event_bus import EventBus\n", encoding="utf-8")
    (tmp_path / "plugins/demo/environment/pyvenv.cfg").write_text("", encoding="utf-8")
    (tmp_path / "packages/sdk/python").mkdir(parents=True)
    (tmp_path / "packages/sdk/tests").mkdir(parents=True)
    assert set(scan(tmp_path)) == set(scanned)


@pytest.mark.parametrize("root", sorted(HOST_ROOTS))
def test_every_actual_host_root_is_forbidden_even_for_typing(root: str) -> None:
    assert host_imports(f"if TYPE_CHECKING:\n    import {root}.internal")


@pytest.mark.parametrize(
    "source",
    [
        "from unittest.mock import patch\npatch('agent.provider.LLMProvider')",
        "import unittest.mock as mock\nmock.patch(target='infra.storage.Store')",
        "from unittest.mock import patch as replace\nother = replace\nother('core.roles.store.RoleStore')",
        "monkeypatch.setattr('bootstrap.app.AppRuntime', fake)",
        "monkeypatch.delattr('session.manager.SessionManager')",
        "from importlib.resources import files\nfiles('shiori_runtime_resources')",
        "from pkgutil import get_data\nget_data('prompts', 'system.md')",
        "import pkgutil\npkgutil.get_data('shiori_runtime_resources', 'common_emojis.json')",
        "import pkgutil as loader\nloader.resolve_name('agent.provider:LLMProvider')",
        "import pkgutil\ngetattr(pkgutil, 'get_data')('prompts', 'system.md')",
        "import importlib\nload = getattr(importlib, 'import_module')\nload('agent.provider')",
        "import importlib\nname = 'agent' + '.provider'\nimportlib.import_module(name)",
        "from importlib import import_module\nroot = 'agent'\nimport_module(f'{root}.provider')",
    ],
)
def test_guard_rejects_indirect_host_references(source: str) -> None:
    assert host_imports(source)


def test_repeated_string_assignment_stays_bounded_and_detects_the_host() -> None:
    source = (
        "import importlib\nname = 'core'\nname = name + '.config'\n"
        "importlib.import_module(name)\n"
    )
    # Exact edges also detect excessive fixed-point growth without a timing-
    # dependent assertion; the resolver visits each string assignment once.
    assert host_imports(source) == {"core": 1, "core.config": 1}
    assert host_imports("name = 'safe'\nname = name + '.module'") == {}


def test_sdk_cannot_import_a_concrete_plugin_but_plugins_keep_public_siblings(
    tmp_path: Path,
) -> None:
    sdk = tmp_path / "packages/sdk/python/shiori_sdk/implementation.py"
    plugin = tmp_path / "plugins/story/backend/plugin.py"
    for path in (sdk, plugin):
        path.parent.mkdir(parents=True)
        path.write_text(
            "from plugins.novelai.backend.public import Generator\n", encoding="utf-8"
        )
    assert set(scan(tmp_path)) == {sdk.relative_to(tmp_path).as_posix()}


def test_metadata_cannot_hide_host_requirements_in_unselected_extras(
    tmp_path: Path,
) -> None:
    sdk = tmp_path / "packages/sdk/pyproject.toml"
    plugin = tmp_path / "plugins/demo/pyproject.toml"
    for path in (sdk, plugin):
        path.parent.mkdir(parents=True)
    sdk.write_text(
        '[project]\nname="shiori-sdk"\ndependencies=["shiori-plugin-demo"]\n',
        encoding="utf-8",
    )
    plugin.write_text(
        '[project]\nname="shiori-plugin-demo"\n[project.optional-dependencies]\nhidden=["shiori-host-testing; sys_platform == \'missing\'"]\n',
        encoding="utf-8",
    )
    errors = dependency_violations(tmp_path)
    assert len(errors) == 2
    assert any("shiori-plugin-demo" in error for error in errors)
    assert any("shiori-host-testing" in error for error in errors)
