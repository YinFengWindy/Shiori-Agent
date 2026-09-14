"""Memory package resolution across source, wheel and frozen resource layouts."""

from importlib.machinery import ModuleSpec
from pathlib import Path
import shutil
import sys

import pytest

from bootstrap import paths
from bootstrap.memory_plugins import load_memory_plugin_module


@pytest.mark.parametrize("engine", ["default", "akasha"])
@pytest.mark.parametrize("layout", ["source", "wheel", "frozen"])
def test_real_memory_modules_follow_resource_roots_from_unrelated_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str, layout: str
):
    package = "default_memory" if engine == "default" else engine
    expected_backend = paths.REPOSITORY_ROOT / "plugins" / package / "backend"
    if layout != "source":
        plugin_root = tmp_path / "distribution" / "plugins"
        expected_backend = plugin_root / package / "backend"
        _ = shutil.copytree(
            paths.REPOSITORY_ROOT / "plugins" / package / "backend",
            expected_backend,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        if layout == "frozen":
            monkeypatch.setattr(sys, "_MEIPASS", str(plugin_root.parent), raising=False)
        else:
            spec = ModuleSpec("plugins", loader=None, is_package=True)
            spec.submodule_search_locations = [
                str(tmp_path / "empty"),
                str(plugin_root),
            ]
            monkeypatch.setattr(paths, "_SOURCE_ROOT", None)

            def installed_plugin_spec(name: str):
                assert name == "plugins"
                return spec

            monkeypatch.setattr(paths, "find_spec", installed_plugin_spec)
    monkeypatch.chdir(tmp_path)
    # These entry points must not depend on a globally importable plugins package.
    monkeypatch.setitem(sys.modules, "plugins", None)

    entry = load_memory_plugin_module(engine, "memory_plugin")
    config = load_memory_plugin_module(engine, "config")

    assert entry.__file__ is not None
    assert config.__file__ is not None
    assert Path(entry.__file__).resolve() == expected_backend / "memory_plugin.py"
    assert Path(config.__file__).resolve() == expected_backend / "config.py"
    assert load_memory_plugin_module(engine, "memory_plugin") is entry
    assert getattr(entry, f"load_{package}_config") is getattr(
        config, f"load_{package}_config"
    )


def test_missing_frozen_engine_does_not_fall_back_to_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    with pytest.raises(ValueError, match="未知 memory engine: akasha"):
        _ = load_memory_plugin_module("akasha", "memory_plugin")


def test_independent_package_roots_do_not_share_config_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    roots = [tmp_path / "first", tmp_path / "second"]
    for index, root in enumerate(roots):
        backend = root / "custom" / "backend"
        backend.mkdir(parents=True)
        _ = (backend / "memory_plugin.py").write_text("", encoding="utf-8")
        _ = (backend / "config.py").write_text(f"value = {index}", encoding="utf-8")
    monkeypatch.setattr("bootstrap.memory_plugins.plugin_roots", lambda: [roots[0]])
    first = load_memory_plugin_module("custom", "config")
    monkeypatch.setattr("bootstrap.memory_plugins.plugin_roots", lambda: [roots[1]])
    second = load_memory_plugin_module("custom", "config")

    assert first is not second
    assert first.value == 0
    assert second.value == 1
