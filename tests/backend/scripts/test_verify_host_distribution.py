"""Production wheels must contain resources and exclude development/user state."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.verify_host_distribution import check_host_wheel

REQUIRED = (
    "agent/provider.py",
    "shiori_runtime_resources/config.example.toml",
    "shiori_runtime_resources/common_emojis.json",
    "shiori_runtime_resources/skills/example/SKILL.md",
)


def _wheel(tmp_path: Path, entries: tuple[str, ...]) -> Path:
    wheel = tmp_path / "host.whl"
    with ZipFile(wheel, "w") as archive:
        for entry in entries:
            archive.writestr(entry, "content")
    return wheel


@pytest.mark.parametrize(
    "entry",
    [
        "tests/test_app.py",
        "shiori_host_testing/memory.py",
        "plugins/demo/backend/plugin.py",
        "agent/plugin_packages/demo.py",
        "agent/tests/test_internal.py",
        "data/state.json",
        "logs/run.txt",
        "apps/desktop/index.js",
        "agent/__pycache__/internal.pyc",
        "core/config.kv.json",
        "core/plugin_config.json",
    ],
)
def test_wheel_rejects_tests_plugins_and_private_state(
    tmp_path: Path, entry: str
) -> None:
    with pytest.raises(AssertionError):
        check_host_wheel(_wheel(tmp_path, (*REQUIRED, entry)), tmp_path / "files.txt")


@pytest.mark.parametrize("missing", REQUIRED)
def test_wheel_requires_every_production_resource(tmp_path: Path, missing: str) -> None:
    with pytest.raises(AssertionError):
        check_host_wheel(
            _wheel(tmp_path, tuple(name for name in REQUIRED if name != missing)),
            tmp_path / "files.txt",
        )


def test_valid_wheel_records_its_contents(tmp_path: Path) -> None:
    log = tmp_path / "files.txt"
    check_host_wheel(_wheel(tmp_path, REQUIRED), log)
    assert log.read_text(encoding="utf-8").splitlines() == list(REQUIRED)
