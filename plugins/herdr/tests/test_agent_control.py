"""Shared agent sending: argv, per-agent records, failures and unconfirmed prompts."""

from pathlib import Path
import asyncio
import json

import pytest

from plugins.herdr.backend.agent_commands import (
    USER,
    AgentCommandLog,
    CommandSource,
    Handover,
)
from plugins.herdr.backend.agent_control import AgentControl
from plugins.herdr.backend.agent_watch import AgentWatcher
from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.config import HerdrConfig
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from plugins.herdr.backend.sessions import SessionGate
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.service_context import FakeServiceContext

PACKAGE_DIR = Path(__file__).resolve().parents[1]

ROLE = CommandSource("role", "role-a", "Mira")


class Herdr:
    """Answers the session check; each command gets the scripted answer."""

    def __init__(self):
        self.argv: list[list[str]] = []
        self.timeouts: list[float | None] = []
        self.answer: CommandError | None = None
        # What watches of the agent read, and how often they read it.
        self.state = "working"
        self.seq: int | None = 1
        self.looks = 0
        # Fails the next state read once, when set.
        self.get_error: CommandError | None = None
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
        if argv[3:5] == ["agent", "get"]:
            if self.get_error:
                error, self.get_error = self.get_error, None
                raise error
            self.looks += 1
            agent = {"agent_status": self.state, "state_change_seq": self.seq}
            return json.dumps({"result": {"agent": agent}})
        if argv[3:5] == ["agent", "read"]:
            return "output"
        self.argv.append(argv)
        self.timeouts.append(timeout)
        if self.answer:
            raise self.answer
        return json.dumps({"result": {"agent": {"agent_status": "working"}}})


async def looks(herdr: Herdr, count: int) -> None:
    """Wait until watches have read the agent `count` more times."""
    async with asyncio.timeout(5):
        seen = herdr.looks
        while herdr.looks < seen + count:
            await asyncio.sleep(0)


@pytest.fixture
async def fixture(tmp_path, monkeypatch):
    ctx = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    # The smallest CLI timeout the config allows, shorter than Herdr's own wait.
    config = HerdrConfig(session="default", cli_timeout_seconds=5)
    cli = HerdrCli(config, ctx.fake_processes, tmp_path)
    herdr = Herdr()
    # Watches build their own CLI; every CLI talks to the same fake Herdr.
    monkeypatch.setattr(
        HerdrCli, "command", lambda _cli, argv, **kwargs: herdr.command(argv, **kwargs)
    )
    log = AgentCommandLog()
    watcher = AgentWatcher()
    watcher.attach(ctx.fake_process_resources, ctx.fake_processes, tmp_path)
    control = AgentControl(
        SessionGate(cli, ctx.fake_process_resources),
        log,
        TaskService(tmp_path),
        watcher,
    )
    yield control, log, herdr
    await watcher.close()
    await ctx.aclose()


async def test_prompt_and_keys_use_explicit_argv_and_record_their_source(fixture):
    control, log, herdr = fixture
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    await control.prompt("wR:p2", '修一下 & 测试 "引号"', ROLE, target)
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


async def test_a_roles_command_hands_the_agent_over_and_the_users_follows_it(fixture):
    control, _log, herdr = fixture
    watcher = control.watcher
    watcher.poll_seconds = 0
    # Without a handling role the user's command is not reported.
    alone = await control.prompt("wR:p2", "先看看", USER)
    assert alone.report == "none"

    mira_target = FakeBackgroundResultTarget("role-a", "thread-a")
    mira = await control.prompt("wR:p2", "修滚动", ROLE, mira_target)
    assert watcher.handover("default", "wR:p2") == Handover("Mira", mira_target)
    ayu = FakeBackgroundResultTarget("role-b", "thread-b")
    keys = await control.send_keys(
        "wR:p2", ["enter"], CommandSource("role", "role-b", "Ayu"), ayu
    )
    handover = watcher.handover("default", "wR:p2")
    assert handover is not None and handover.as_dict() == {
        "role_id": "role-b",
        "role_name": "Ayu",
    }
    user = await control.prompt("wR:p2", "补测试", USER)
    assert mira.report == keys.report == user.report == "pending"

    herdr.state = "idle"
    async with asyncio.timeout(5):
        while user.report == "pending":
            await asyncio.sleep(0)
    # Each command goes to the role it was reported to when sent, once.
    [mira_report] = mira_target.reports.values()
    [ayu_report] = ayu.reports.values()
    assert [item["content"] for item in json.loads(mira_report)["commands"]] == [
        "修滚动"
    ]
    assert [
        (item["content"], item["sender"]) for item in json.loads(ayu_report)["commands"]
    ] == [("enter", "Ayu"), ("补测试", "用户在 Herdr 面板直接发送")]
    assert alone.report == "none"


async def test_a_role_command_without_a_captured_destination_is_not_sent(fixture):
    control, log, herdr = fixture
    with pytest.raises(PermissionError):
        await control.prompt("wR:p2", "修滚动", ROLE)
    assert herdr.argv == []
    assert log.records("default", "wR:p2") == []


async def test_keys_answering_a_blocked_agent_are_not_reported_on_that_block(fixture):
    control, _log, herdr = fixture
    control.watcher.poll_seconds = 0
    herdr.state, herdr.seq = "blocked", 5
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    command = await control.send_keys("wR:p2", ["enter"], ROLE, target)

    # The first looks still read the block the keys answered.
    await looks(herdr, 3)
    assert command.report == "pending" and target.reports == {}
    herdr.state, herdr.seq = "working", 6
    await looks(herdr, 2)
    herdr.state, herdr.seq = "blocked", 7
    async with asyncio.timeout(5):
        while command.report == "pending":
            await asyncio.sleep(0)
    [text] = target.reports.values()
    assert json.loads(text)["outcome"] == "blocked"


async def test_keys_go_out_even_when_the_state_before_them_is_unreadable(fixture):
    control, _log, herdr = fixture
    herdr.get_error = CommandError("read failed", code="command_failed")
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    command = await control.send_keys("wR:p2", ["ctrl+c"], ROLE, target)
    assert command.status == "sent"
    assert herdr.argv[-1][3:] == ["agent", "send-keys", "wR:p2", "ctrl+c"]


async def test_a_block_of_unknown_sequence_after_keys_waits_for_a_change(fixture):
    control, _log, herdr = fixture
    control.watcher.poll_seconds = 0
    herdr.state, herdr.seq = "blocked", None
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    command = await control.send_keys("wR:p2", ["enter"], ROLE, target)

    await looks(herdr, 3)
    assert command.report == "pending" and target.reports == {}
    herdr.state = "working"
    await looks(herdr, 2)
    herdr.state = "blocked"
    async with asyncio.timeout(5):
        while command.report == "pending":
            await asyncio.sleep(0)
    [text] = target.reports.values()
    assert json.loads(text)["outcome"] == "blocked"
