"""Shared agent sending: argv, per-agent records, failures and unconfirmed prompts."""

import asyncio
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
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from plugins.herdr.backend.sessions import SessionGate
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.service_context import FakeServiceContext

ROLE = CommandSource("role", "role-a", "Mira")


class Herdr:
    """Answers the session check; each command gets the scripted answer."""

    def __init__(self):
        self.argv: list[list[str]] = []
        self.timeouts: list[float | None] = []
        self.answer: CommandError | None = None
        # Holds the session check until set, to act between check and send.
        self.checked = asyncio.Event()
        self.checked.set()

    async def command(self, argv, *, timeout=None, **_kwargs):
        if argv[1:] == ["--version"]:
            await self.checked.wait()
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
        self.timeouts.append(timeout)
        if self.answer:
            raise self.answer
        return json.dumps({"result": {"agent": {"agent_status": "working"}}})


@pytest.fixture
async def fixture(tmp_path):
    ctx = FakeServiceContext("herdr", tmp_path)
    # The smallest CLI timeout the config allows, shorter than Herdr's own wait.
    config = HerdrConfig(session="default", cli_timeout_seconds=5)
    cli = HerdrCli(config, ctx.processes, tmp_path)
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


async def test_the_prompt_process_outlives_herdrs_own_wait(fixture):
    control, _log, herdr = fixture
    await control.prompt("wR:p2", "继续", USER)
    await control.send_keys("wR:p2", ["ctrl+c"], USER)
    # Herdr's --timeout 10000 must fire before the 5 s CLI timeout kills it.
    prompt_timeout, keys_timeout = herdr.timeouts
    assert prompt_timeout is not None and prompt_timeout > 10
    assert keys_timeout is None


async def test_a_task_run_starting_during_the_session_check_refuses_the_input(
    fixture, tmp_path
):
    control, log, herdr = fixture
    task = CodingTask(
        "task",
        "修复滚动",
        tmp_path,
        "codex",
        FakeBackgroundResultTarget("role-a", "thread"),
        tmp_path,
        "branch",
        "run",
        config=HerdrConfig(session="default"),
        pane_id="wR:p2",
    )
    control.service.tasks[task.id] = task
    herdr.checked.clear()
    sending = asyncio.create_task(control.prompt("wR:p2", "插话", USER))
    await asyncio.sleep(0)
    # The run starts after the first look, while the session is being checked.
    task.worker = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
    herdr.checked.set()
    with pytest.raises(ValueError, match="插件任务"):
        await sending
    assert herdr.argv == []
    assert log.records("default", "wR:p2") == []
    task.worker.cancel()
