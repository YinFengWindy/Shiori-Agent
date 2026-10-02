"""Run external build/install/test commands with recorded logs and a clean environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

UV = str(Path(sys.executable).with_name("uv.exe" if os.name == "nt" else "uv"))
if not Path(UV).is_file():
    UV = "uv"


class CommandFailed(RuntimeError):
    """An external command exited unexpectedly; ``log`` holds its complete output."""

    def __init__(self, message: str, *, log: Path) -> None:
        super().__init__(message)
        self.log = log


def clean_environment() -> dict[str, str]:
    """Drops import injection and service credentials before any external test process."""
    result = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PYTHON", "PYTEST"))
        and not any(
            word in key.upper()
            for word in (
                "API_KEY",
                "TOKEN",
                "SECRET",
                "PASSWORD",
                "CREDENTIAL",
                "OPENAI",
            )
        )
    }
    result.update(PYTHONNOUSERSITE="1", PYTHONUTF8="1", UV_LINK_MODE="copy")
    return result


def run(command: list[str], *, cwd: Path, log: Path, expected: int = 0) -> str:
    """Records exact execution evidence and raises on unexpected test/install outcomes."""
    result = subprocess.run(
        command,
        cwd=cwd,
        env=clean_environment(),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log.write_text(result.stdout, encoding="utf-8")
    if result.returncode != expected:
        raise CommandFailed(
            f"Expected exit {expected}, got {result.returncode}; see {log}\n{result.stdout[-6000:]}",
            log=log,
        )
    return result.stdout
