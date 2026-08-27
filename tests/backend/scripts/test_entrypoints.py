from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _clean_python_environment() -> dict[str, str]:
    """Run entry-point smoke tests without pytest's injected module paths."""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_python(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPOSITORY_ROOT,
        env=_clean_python_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_maintenance_scripts_support_direct_help_invocation() -> None:
    for script in ("scripts/build_akasha_db.py", "scripts/build_fts_idf.py"):
        result = _run_python(script, "--help")

        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout
