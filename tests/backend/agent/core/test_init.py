"""Core values and lifecycle modules import independently of process import order."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "agent.lifecycle.phases.before_turn",
        "agent.lifecycle.phases.after_reasoning",
        "agent.core.passive_support",
        "agent.core.passive_turn.pipeline",
    ],
)
def test_runtime_modules_can_be_first_import_in_a_fresh_process(module):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import importlib; importlib.import_module({module!r})",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
