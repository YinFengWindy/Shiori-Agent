"""The optional pytest fixture closes a plugin scope even after test failure."""

from pathlib import Path
import subprocess
import sys


def test_sdk_context_always_disposes_registered_effects(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\nasyncio_mode = auto\nasyncio_default_fixture_loop_scope = function\n",
        encoding="utf-8",
    )
    (tmp_path / "test_cleanup.py").write_text(
        "from pathlib import Path\n\n"
        "async def test_cleanup(sdk_context):\n"
        "    def dispose():\n"
        "        Path('disposed.txt').write_text('closed', encoding='utf-8')\n"
        "    sdk_context.effect('probe', dispose)\n"
        "    assert False, 'intentional failure'\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-I", "-m", "pytest", "-q"],
        cwd=tmp_path,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "intentional failure" in result.stdout
    assert (tmp_path / "disposed.txt").read_text(encoding="utf-8") == "closed"
