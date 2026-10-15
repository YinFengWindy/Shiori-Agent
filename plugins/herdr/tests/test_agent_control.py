"""Shared agent sending: argv, per-agent records, failures and unconfirmed prompts."""

import json

import pytest

from plugins.herdr.backend.agent_control import (
    USER,
    AgentCommandLog,
    AgentControl,
    CommandSource,
)
from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.config import HerdrConfig
from plugins.herdr.backend.service import TaskService
from plugins.herdr.backend.sessions import SessionGate
from shiori_sdk.testing.service_context import FakeServiceContext

ROLE = CommandSource("role", "role-a", "Mira")


class Herdr:
    """Answers the session check; each command gets the scripted answer."""

    def __init__(self):
        self.argv: list[list[str]] = []
        self.answer: CommandError | None = None

    async def command(self, argv, **_kwargs):
        if argv[1:] == ["--version"]:
            return "herdr 0.9.5"
        if argv[-3:] == ["status", "server", "--json"]:
            return json.dumps(
                {
                    "running": True,
                    "version": "0.9.5",
                    "compatible": True,
                    "endpoint_compatible": True,
                }
            )
        self.argv.append(argv)
        if self.answer:
            raise self.answer
        return json.dumps({"result": {"agent": {"agent_status": "working"}}})


@pytest.fixture
async def fixture(tmp_path):
    ctx = FakeServiceContext("herdr", tmp_path)
    cli = HerdrCli(HerdrConfig(session="default"), ctx.processes, tmp_path)
    herdr = Herdr()
    cli.command = herdr.command  # type: ignore[method-assign]
    log = AgentCommandLog()
    control = AgentControl(
        SessionGate(cli, ctx.process_resources),
        log,
        TaskService(tmp_path, ctx.processes),
    )
    yield control, log, herdr
    await ctx.aclose()


async def test_prompt_and_keys_use_explicit_argv_and_record_their_source(fixture):
    control, log, herdr = fixture
    await control.prompt("wR:p2", '修一下 & 测试 "引号"', ROLE)
    await control.send_keys("wR:p2", ["ctrl+c"], USER)

    assert herdr.argv == [
        [
            *("herdr", "--session", "default", "agent", "prompt", "wR:p2"),
            '修一下 & 测试 "引号"',
            *("--wait", "--until", "working", "--until", "blocked"),
            *("--timeout", "10000"),
        ],
        ["herdr", "--session", "default", "agent", "send-keys", "wR:p2", "ctrl+c"],
    ]
    records = log.records("default", "wR:p2")
    assert [(item["kind"], item["source"], item["status"]) for item in records] == [
        ("prompt", {"kind": "role", "role_id": "role-a", "role_name": "Mira"}, "sent"),
        ("keys", {"kind": "user", "role_id": "", "role_name": ""}, "sent"),
    ]
    assert log.records("other", "wR:p2") == []


async def test_each_agent_keeps_its_latest_hundred_commands(fixture):
    control, log, _herdr = fixture
    for index in range(101):
        await control.send_keys("wR:p2", [f"key{index}"], USER)
    records = log.records("default", "wR:p2")
    assert len(records) == 100
    assert records[0]["content"] == "key1"
    assert records[-1]["content"] == "key100"


async def test_a_refused_prompt_is_recorded_as_failed(fixture):
    control, log, herdr = fixture
    herdr.answer = CommandError("agent is blocked", code="agent_blocked")
    with pytest.raises(CommandError, match="等待确认"):
        await control.prompt("wR:p2", "继续", USER)
    [record] = log.records("default", "wR:p2")
    assert record["status"] == "failed"
    assert "等待确认" in record["error"]


@pytest.mark.parametrize("code", ["timeout", "agent_prompt_stalled"])
async def test_an_unconfirmed_prompt_is_never_resent(fixture, code):
    control, log, herdr = fixture
    herdr.answer = CommandError("no activity", code=code)
    with pytest.raises(CommandError, match="可能已经送达"):
        await control.prompt("wR:p2", "继续", USER)
    assert len(herdr.argv) == 1
    [record] = log.records("default", "wR:p2")
    assert record["status"] == "unconfirmed"
