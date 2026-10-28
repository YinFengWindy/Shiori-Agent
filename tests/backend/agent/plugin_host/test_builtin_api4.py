"""Built-in plugins are manifest api 4 and call ctx.require for those keys.

This is the P4-3 slice of the §5.2 contract check: every package under
``plugins/`` is api 4, its backend ``require`` / ``get`` / ``provide`` names
match the manifest, and it no longer reads capability attributes. It checks
repository content, so it is not in the default suite; ``select_tests`` runs
it when ``plugins/`` or the plugin host changes. The api 4 host contract
(manifest rejection, ``ctx.require(TOOLS)`` through the kernel) is in
``test_kernel.py``.

Hot-reload order equality, dispose-zero for every plugin, runtime channel
registration and named frontend exports stay with the P7 loader.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent.plugin_host.manifest import load_manifest
from agent.plugin_host.versions import satisfies
from shiori_sdk import __version__
from shiori_sdk.core import services as service_keys
from shiori_sdk.kernel import Key
from tests.support.plugin_kernel import REPOSITORY_ROOT

_PLUGINS = REPOSITORY_ROOT / "plugins"
_CORE_MODULES = (
    "shiori_sdk.core.conversation",
    "shiori_sdk.core.crash_reporting",
    "shiori_sdk.core.memory",
    "shiori_sdk.core.models",
    "shiori_sdk.core.services",
    "shiori_sdk.core.sessions",
    "shiori_sdk.core.tools",
)
# Former capability attributes and the public keys that were never properties.
_BANNED_ATTRS = frozenset(
    value.name for value in vars(service_keys).values() if isinstance(value, Key)
) | {
    "commands",
    "crash_reporting",
    "main_model",
    "main_provider",
    "memory_engine",
    "sessions",
}
_CONTEXT_NAMES = frozenset({"ctx", "_ctx"})


def _plugin_dirs() -> list[Path]:
    return sorted(
        path for path in _PLUGINS.iterdir() if (path / "manifest.yaml").is_file()
    )


def _key_catalog() -> dict[str, str]:
    """Constant name → ``Key.name`` for every core key."""
    import importlib

    catalog: dict[str, str] = {}
    for module_name in _CORE_MODULES:
        module = importlib.import_module(module_name)
        for attr, value in vars(module).items():
            if isinstance(value, Key):
                catalog[attr] = value.name
    return catalog


_CATALOG = _key_catalog()
_KNOWN_KEYS = frozenset(_CATALOG.values())


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local name → key name, from ``from shiori_sdk... import KEY``."""
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if not node.module.startswith("shiori_sdk"):
            continue
        for alias in node.names:
            key_name = _CATALOG.get(alias.name)
            if key_name is not None:
                found[alias.asname or alias.name] = key_name
    return found


def _is_context(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _CONTEXT_NAMES
    return isinstance(node, ast.Attribute) and node.attr in _CONTEXT_NAMES


def _key_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Key"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.args[0].value
    return None


def _backend_uses(plugin_dir: Path) -> tuple[set[str], set[str], set[str], list[str]]:
    """require / get / provide key names, and capability-attribute violations."""
    required: set[str] = set()
    optional: set[str] = set()
    provided: set[str] = set()
    violations: list[str] = []
    buckets = {"require": required, "get": optional, "provide": provided}
    for path in sorted((plugin_dir / "backend").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _aliases(tree)
        relative = path.relative_to(plugin_dir).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _BANNED_ATTRS:
                if _is_context(node.value):
                    violations.append(f"{relative}:{node.lineno} ctx.{node.attr}")
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            bucket = buckets.get(node.func.attr)
            if bucket is None or not node.args or not _is_context(node.func.value):
                continue
            name = _key_name(node.args[0], aliases)
            if name is None:
                violations.append(
                    f"{relative}:{node.lineno} {node.func.attr}() 的 Key 无法解析"
                )
            else:
                bucket.add(name)
    return required, optional, provided, violations


@pytest.mark.parametrize("plugin_dir", _plugin_dirs(), ids=lambda path: path.name)
def test_builtin_plugin_manifest_matches_require(plugin_dir: Path) -> None:
    """api 4, inject lines up with require/get/provide, and the entry file exists."""
    manifest = load_manifest(plugin_dir)
    assert manifest is not None
    assert satisfies(__version__, manifest.sdk)
    # The parser rejects the other removed fields; renderer is kept until P7.
    assert "renderer" not in manifest.metadata
    assert not ({"sessions", "session_store"} <= set(manifest.inject))
    for name in (*manifest.inject, *manifest.optional_inject, *manifest.provides):
        assert name in _KNOWN_KEYS, name

    if manifest.channels:
        assert "channels" in manifest.inject
        assert manifest.category == "channel"
    ui = plugin_dir / "ui" / "index.tsx"
    if ui.is_file():
        assert manifest.frontend_entry == "ui/index.tsx"
    if manifest.frontend_entry is not None:
        assert (plugin_dir / manifest.frontend_entry).is_file()

    required, optional, provided, violations = _backend_uses(plugin_dir)
    assert not violations, violations
    assert required <= set(manifest.inject)
    assert optional <= set(manifest.optional_inject)
    assert provided <= set(manifest.provides)
    assert set(manifest.provides) <= provided
