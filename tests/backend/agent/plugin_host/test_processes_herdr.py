"""Real Windows process ownership and batch argv boundaries for Herdr validation."""

import json
import sys

import pytest

from infra.process.plugin_capability import HostProcesses
from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.config import HerdrConfig

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows batch boundary"
)


@pytest.fixture
def batch_cli(tmp_path):
    directory = tmp_path / "batch tools"
    directory.mkdir()
    script = directory / "echo argv.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "Path(__file__).with_name('started').write_text('started', encoding='utf-8')\n"
        "if sys.argv[1:] == ['fail']: raise SystemExit(7)\n"
        "print(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    batch = directory / "validation.cmd"
    batch.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    cli = HerdrCli(HerdrConfig(), HostProcesses().as_capability(), tmp_path)
    return cli, batch, directory / "started"


async def test_windows_batch_passes_safe_argv_and_space_paths(batch_cli, tmp_path):
    cli, batch, started = batch_cli
    arguments = [
        "test",
        "--filter",
        "@scope/package",
        str(tmp_path / "files with spaces" / "input file.txt"),
        "directory with spaces\\",
        "",
    ]

    output = await cli.command([str(batch), *arguments])

    assert json.loads(output) == arguments
    assert started.exists()


async def test_windows_batch_failure_remains_failure(batch_cli):
    cli, batch, started = batch_cli

    with pytest.raises(CommandError) as raised:
        await cli.command([str(batch), "fail"])

    assert raised.value.exit_code == 7
    assert started.exists()


async def test_windows_batch_cannot_mask_failure_with_a_second_command(batch_cli):
    cli, batch, started = batch_cli

    with pytest.raises(CommandError) as raised:
        await cli.command([str(batch), "fail", "&", "echo", "SHIORI_LITERAL_ARGUMENT"])

    assert raised.value.code == "unsafe_windows_batch_argument"
    assert not started.exists()
