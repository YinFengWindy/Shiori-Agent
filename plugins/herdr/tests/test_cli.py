"""CLI protocol, argument preservation and timeout ownership boundaries."""

import asyncio
import sys

import pytest

from shiori_sdk.testing.processes import FakeProcesses
from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.config import HerdrConfig
from unittest.mock import AsyncMock


class FixtureProcesses(FakeProcesses):
    """Only execute the test's Python fixture, never a coding agent or Herdr."""

    def __init__(self, script):
        self.script = script
        self.processes = []

    async def spawn(self, *command, **kwargs):
        assert command[0] == "fixture-herdr"
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(self.script), *command[1:], **kwargs
        )
        self.processes.append(process)
        return process, None


@pytest.fixture
def cli(tmp_path):
    script = tmp_path / "fake_cli.py"
    script.write_text(
        """import json, sys, time
args = sys.argv[1:]
if "hang" in args:
    time.sleep(20)
elif "fail" in args:
    print(json.dumps({"error":{"code":"agent_blocked","message":"needs login"}}), file=sys.stderr)
    sys.exit(1)
elif "invalid" in args:
    print("not json")
elif "read" in args:
    print("terminal text")
else:
    print(json.dumps({"ok":True,"result":{"args":args}}))
""",
        encoding="utf-8",
    )
    processes = FixtureProcesses(script)
    return HerdrCli(
        HerdrConfig(executable="fixture-herdr", session="dedicated"),
        processes,
        tmp_path,
    )


async def test_cli_pins_session_and_preserves_unicode_argument_without_shell(cli):
    requirement = "第一行\n引号 \" ' ` $() ; & 中文"
    result = await cli.call("agent", "prompt", "owned-agent", requirement)
    assert result["args"] == [
        "--session",
        "dedicated",
        "agent",
        "prompt",
        "owned-agent",
        requirement,
    ]
    assert (await cli.read("owned-agent")).strip() == "terminal text"


async def test_structured_failure_and_malformed_response_are_explicit(cli):
    with pytest.raises(CommandError) as raised:
        await cli.call("fail")
    assert raised.value.code == "agent_blocked"
    with pytest.raises(CommandError, match="无法识别"):
        await cli.call("invalid")


async def test_timeout_terminates_only_cli_and_does_not_retry(cli):
    with pytest.raises(CommandError) as raised:
        await cli.command(["fixture-herdr", "hang"], timeout=0.1)
    assert raised.value.code == "timeout"
    assert "可能仍在运行" in str(raised.value)
    assert len(cli.processes.processes) == 1
    assert cli.processes.processes[0].returncode is not None


@pytest.mark.parametrize(
    "version, running, server_version, valid",
    [
        ("0.9.4", True, "0.9.4", True),
        ("0.8.2", True, "0.9.4", False),
        ("0.9.4", True, "0.8.2", False),
        ("0.9.4", False, None, False),
    ],
)
async def test_both_cli_and_named_server_versions_are_checked(
    cli, monkeypatch, version, running, server_version, valid
):
    import json

    command = AsyncMock(
        side_effect=[
            f"herdr {version}",
            json.dumps(
                {
                    "running": running,
                    "version": server_version,
                    "compatible": True,
                    "endpoint_compatible": True,
                }
            ),
        ]
    )
    monkeypatch.setattr(cli, "command", command)
    if valid:
        await cli.require_supported_version()
    else:
        with pytest.raises(CommandError):
            await cli.require_supported_version()
    assert command.call_args_list[0].args[0] == ["fixture-herdr", "--version"]
    if command.call_count > 1:
        assert command.call_args_list[1].args[0] == [
            "fixture-herdr",
            "--session",
            "dedicated",
            "status",
            "server",
            "--json",
        ]
