"""External commands run without credentials or import injection, with logged output."""

from pathlib import Path
import sys

import pytest

from scripts import commands


def test_clean_environment_drops_credentials_and_python_injection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "OPENAI_API_KEY",
        "GITHUB_TOKEN",
        "client_secret",
        "DB_PASSWORD",
        "AWS_CREDENTIALS",
        "PYTHONPATH",
        "PYTEST_ADDOPTS",
    ):
        monkeypatch.setenv(key, "leak")
    monkeypatch.setenv("SHIORI_HARMLESS", "kept")
    environment = commands.clean_environment()
    assert not {
        key for key, value in environment.items() if value == "leak"
    }, environment
    assert environment["SHIORI_HARMLESS"] == "kept"
    assert environment["PYTHONNOUSERSITE"] == "1"


def test_run_records_output_and_rejects_an_unexpected_exit(tmp_path: Path) -> None:
    log = tmp_path / "command.log"
    script = "import sys; print('evidence'); sys.exit(3)"
    with pytest.raises(commands.CommandFailed) as failure:
        commands.run([sys.executable, "-c", script], cwd=tmp_path, log=log)
    assert failure.value.log == log
    assert "evidence" in log.read_text(encoding="utf-8")
    assert "evidence" in commands.run(
        [sys.executable, "-c", script], cwd=tmp_path, log=log, expected=3
    )
