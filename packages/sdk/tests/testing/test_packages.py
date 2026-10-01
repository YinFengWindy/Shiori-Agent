"""Public package staging keeps plugin assets while excluding machine-local state."""

from pathlib import Path

import pytest

from shiori_sdk.testing.packages import stage_plugin_package


def _write(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(relative, encoding="utf-8")


@pytest.mark.parametrize("environment", [".venv", "custom-python", "nested/runtime"])
def test_stage_excludes_virtual_environments(environment: str, tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    _write(source, "backend/plugin.py")
    _write(source, "manifest.yaml")
    _write(source, f"{environment}/Lib/site-packages/review-marker.txt")
    if environment != ".venv":
        _write(source, f"{environment}/pyvenv.cfg")

    assert stage_plugin_package(source, target) == target
    assert (target / "backend/plugin.py").read_text(
        encoding="utf-8"
    ) == "backend/plugin.py"
    assert (target / "manifest.yaml").is_file()
    assert not (target / environment).exists()


def test_stage_omits_generated_state_but_preserves_resources(tmp_path: Path) -> None:
    source, target = tmp_path / "source", tmp_path / "target"
    excluded = [
        "build/lib/plugin.py",
        "dist/plugin.whl",
        ".data/runtime.json",
        ".git/config",
        "backend/__pycache__/plugin.pyc",
        "tests/.pytest_cache/state",
        "ui/node_modules/package/index.js",
        "plugin.egg-info/PKG-INFO",
        ".kv.json",
        "plugin.disabled",
        "plugin_config.json",
        "config.local.toml",
        "backend/config.local.toml",
    ]
    preserved = [
        "backend/plugin.py",
        "manifest.yaml",
        "tests/test_plugin.py",
        "TESTING.md",
        "backend/assets/build/resource.txt",
        "backend/assets/dist/resource.txt",
        "backend/assets/env/resource.txt",
        "tests/fixtures/plugin_config.json",
        "tests/fixtures/config.local.toml",
        ".venv-illustration/resource.txt",
    ]
    for name in excluded + preserved:
        _write(source, name)

    _ = stage_plugin_package(source, target)

    assert all(not (target / name).exists() for name in excluded)
    assert all(
        (target / name).read_text(encoding="utf-8") == name for name in preserved
    )
