from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _clean_python_environment() -> dict[str, str]:
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


def test_run_one_qa_supports_module_help_without_pythonpath() -> None:
    result = _run_python("-m", "benchmarks.longmemeval.run_one_qa", "--help")

    assert result.returncode == 0, result.stderr
    assert "Run QA only for one LongMemEval instance." in result.stdout


def test_ingest_imports_backend_packages_without_pythonpath() -> None:
    result = _run_python("-c", "import benchmarks.longmemeval.ingest")

    assert result.returncode == 0, result.stderr
