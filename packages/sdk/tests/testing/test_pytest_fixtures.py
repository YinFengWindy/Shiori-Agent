"""The optional pytest fixture grants a plugin's manifest and always closes its scope."""

from pathlib import Path
import subprocess
import sys

import pytest

from shiori_sdk.testing.pytest_fixtures import find_plugin_dir, load_manifest_grants


def _run_plugin_suite(
    plugin: Path, test_source: str
) -> subprocess.CompletedProcess[str]:
    """Runs pytest as a standalone plugin package with tests under ``tests/``."""
    (plugin / "pytest.ini").write_text(
        "[pytest]\nasyncio_mode = auto\nasyncio_default_fixture_loop_scope = function\n",
        encoding="utf-8",
    )
    (plugin / "tests").mkdir()
    (plugin / "tests" / "test_probe.py").write_text(test_source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-m", "pytest", "-q"],
        cwd=plugin,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_sdk_context_always_disposes_registered_effects(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text(
        "id: probe\ncapabilities: []\n", encoding="utf-8"
    )
    result = _run_plugin_suite(
        tmp_path,
        "from pathlib import Path\n\n"
        "async def test_cleanup(sdk_context):\n"
        "    def dispose():\n"
        "        Path('disposed.txt').write_text('closed', encoding='utf-8')\n"
        "    sdk_context.effect('probe', dispose)\n"
        "    assert False, 'intentional failure'\n",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "intentional failure" in result.stdout
    assert (tmp_path / "disposed.txt").read_text(encoding="utf-8") == "closed"


def test_sdk_context_rejects_a_capability_the_manifest_does_not_declare(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifest.yaml").write_text(
        "id: probe\ncapabilities:\n  - events\n", encoding="utf-8"
    )
    result = _run_plugin_suite(
        tmp_path,
        "async def test_setup(sdk_context):\n"
        "    assert sdk_context.granted == ('events',)\n"
        "    sdk_context.lifecycle.contribute('after_turn', [])\n",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "CapabilityNotGranted" in result.stdout
    assert "插件 probe 未声明 capability 'lifecycle'" in result.stdout


def test_find_plugin_dir_stops_at_the_test_root(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    (plugin / "tests").mkdir(parents=True)
    (tmp_path / "manifest.yaml").write_text("id: outer\n", encoding="utf-8")
    test_file = plugin / "tests" / "test_x.py"
    with pytest.raises(LookupError, match="sdk_plugin_dir"):
        find_plugin_dir(test_file, plugin)
    (plugin / "manifest.yaml").write_text("id: inner\n", encoding="utf-8")
    assert find_plugin_dir(test_file, plugin) == plugin.resolve()


def test_manifest_without_a_capability_list_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "manifest.yaml").write_text("id: probe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="capabilities must be a list"):
        load_manifest_grants(tmp_path)
