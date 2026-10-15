"""Watching a handed-over agent: when it is reported, what the report says, only once."""

import asyncio
import json

import pytest

from plugins.herdr.backend.agent_commands import (
    USER,
    AgentCommand,
    CommandSource,
    Handover,
)
from plugins.herdr.backend.agent_watch import OUTPUT_TAIL, AgentWatcher
from plugins.herdr.backend.cli import HerdrCli
from plugins.herdr.backend.config import HerdrConfig
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.service_context import FakeServiceContext

CONFIG = HerdrConfig(session="default", task_timeout_seconds=60)
ROLE = CommandSource("role", "role-a", "Mira")


class Agent:
    """One Herdr agent whose successive `agent get` answers are scripted.

    Every look advances the fake clock by ten seconds; the last state repeats.
    """

    def __init__(self, *states: str):
        self.states = list(states)
        self.now = 0.0
        self.looks = 0
        self.output = "x" * OUTPUT_TAIL + "最后一行"
        # When set, the next output read is held until the second event is set.
        self.read_gate: tuple[asyncio.Event, asyncio.Event] | None = None

    async def command(self, argv, **_kwargs):
        if argv[3:5] == ["agent", "read"]:
            if self.read_gate:
                (reading, release), self.read_gate = self.read_gate, None
                reading.set()
                await release.wait()
            return self.output
        assert argv[3:6] == ["agent", "get", "wR:p2"], argv
        self.now += 10
        self.looks += 1
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if state == "gone":
            return json.dumps({"error": {"code": "agent_not_found", "message": "x"}})
        return json.dumps(
            {
                "result": {
                    "agent": {
                        "agent": "claude",
                        "agent_status": state,
                        "pane_id": "wR:p2",
                        "terminal_title_stripped": "herdr插件问题",
                    }
                }
            }
        )


@pytest.fixture
async def watcher(tmp_path, monkeypatch):
    ctx = FakeServiceContext("herdr", tmp_path)
    watcher = AgentWatcher()
    watcher.attach(ctx.process_resources, ctx.processes, tmp_path)
    watcher.poll_seconds = 0
    watcher.start_grace_seconds = 30
    yield watcher, monkeypatch
    await watcher.close()
    await ctx.aclose()


def script(watcher_fixture, *states: str) -> tuple[AgentWatcher, Agent]:
    watcher, monkeypatch = watcher_fixture
    agent = Agent(*states)

    async def command(_cli, argv, **kwargs):
        return await agent.command(argv, **kwargs)

    monkeypatch.setattr(HerdrCli, "command", command)
    watcher.clock = lambda: agent.now
    return watcher, agent


def sent(content: str, source: CommandSource = ROLE, kind: str = "prompt"):
    command = AgentCommand(kind, content, source)  # type: ignore[arg-type]
    command.settle("sent")
    return command


async def settled(*commands: AgentCommand) -> None:
    async with asyncio.timeout(5):
        while any(command.report == "pending" for command in commands):
            await asyncio.sleep(0)


@pytest.mark.parametrize(
    ("states", "outcome", "agent_state"),
    [
        (("working", "working", "idle"), "finished", "idle"),
        (("working", "blocked"), "blocked", "blocked"),
        (("working", "gone"), "gone", "working"),
        (("working",), "timeout", "working"),
        (("idle",), "idle", "idle"),
    ],
)
async def test_each_way_an_agent_ends_up_is_reported_once(
    watcher, states, outcome, agent_state
):
    watcher, agent = script(watcher, *states)
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    command = sent("修一下滚动")
    watcher.take_over("default", "wR:p2", Handover("Mira", target))
    watcher.follow(CONFIG, "wR:p2", command, target, working=False)
    assert command.report == "pending"
    await settled(command)

    assert command.report == "reported"
    [(report_id, text)] = target.reports.items()
    assert report_id == f"herdr-agent:{command.id}"
    report = json.loads(text)
    assert report["outcome"] == outcome
    assert report["agent_state"] == agent_state
    assert report["title"] == "herdr插件问题"
    assert [(item["content"], item["sender"]) for item in report["commands"]] == [
        ("修一下滚动", "Mira")
    ]
    if outcome == "gone":
        assert report["output"] == ""
        assert watcher.handover("default", "wR:p2") is None
    else:
        assert len(report["output"]) == OUTPUT_TAIL
        assert report["output"].endswith("最后一行")
    looks = agent.looks
    await asyncio.sleep(0.01)
    assert agent.looks == looks, "the watch ended with its report"


async def test_commands_arriving_while_watched_are_reported_together_once(watcher):
    watcher, agent = script(watcher, "working", "working", "working", "idle")
    mira = FakeBackgroundResultTarget("role-a", "thread-a")
    first, second = sent("先修滚动"), sent("顺便补测试", USER)
    watcher.follow(CONFIG, "wR:p2", first, mira, working=True)
    async with asyncio.timeout(5):
        while agent.looks < 2:
            await asyncio.sleep(0)
    watcher.follow(CONFIG, "wR:p2", second, mira, working=True)
    await settled(first, second)

    [(report_id, text)] = mira.reports.items()
    assert report_id == f"herdr-agent:{second.id}"
    assert [
        (item["content"], item["sender"]) for item in json.loads(text)["commands"]
    ] == [("先修滚动", "Mira"), ("顺便补测试", "用户在 Herdr 面板直接发送")]
    assert first.report == second.report == "reported"

    # A later command is a new watch and a new report of that command alone.
    agent.states = ["working", "idle"]
    third = sent("再跑一遍")
    watcher.follow(CONFIG, "wR:p2", third, mira, working=False)
    await settled(third)
    assert len(mira.reports) == 2
    assert [
        item["content"]
        for item in json.loads(mira.reports[f"herdr-agent:{third.id}"])["commands"]
    ] == ["再跑一遍"]


async def test_an_interrupt_of_a_working_agent_reads_as_it_stopping(watcher):
    # Seen working when the prompt was sent; idle from the first look after Ctrl+C.
    watcher, _agent = script(watcher, "idle")
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    prompt, interrupt = sent("长任务"), sent("ctrl+c", kind="keys")
    watcher.follow(CONFIG, "wR:p2", prompt, target, working=True)
    watcher.follow(CONFIG, "wR:p2", interrupt, target, working=False)
    await settled(prompt, interrupt)
    [text] = target.reports.values()
    assert json.loads(text)["outcome"] == "finished"


async def test_a_failed_report_is_recorded_and_not_resent(watcher):
    watcher, _agent = script(watcher, "working", "idle")
    attempts = []

    class Unreachable(FakeBackgroundResultTarget):
        async def report(self, result_id: str, text: str) -> bool:
            attempts.append(result_id)
            raise RuntimeError("角色绑定已失效")

    command = sent("修一下")
    watcher.follow(CONFIG, "wR:p2", command, Unreachable(), working=False)
    await settled(command)
    await asyncio.sleep(0.01)
    assert (command.report, command.report_error) == ("failed", "角色绑定已失效")
    assert attempts == [f"herdr-agent:{command.id}"]


async def test_closing_stops_the_watch_without_reporting(watcher):
    watcher, agent = script(watcher, "working")
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    command = sent("长任务")
    watcher.follow(CONFIG, "wR:p2", command, target, working=True)
    async with asyncio.timeout(5):
        while agent.looks < 1:
            await asyncio.sleep(0)
    await watcher.close()
    looks = agent.looks
    await asyncio.sleep(0.01)
    assert agent.looks == looks
    assert target.reports == {}
    assert command.report == "failed"
    assert "停止监视" in command.report_error


async def test_a_command_arriving_while_the_output_is_read_is_reported_next(watcher):
    watcher, agent = script(watcher, "working", "idle")
    reading, release = asyncio.Event(), asyncio.Event()
    agent.read_gate = (reading, release)
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    first, second = sent("先修滚动"), sent("再补测试")
    watcher.follow(CONFIG, "wR:p2", first, target, working=True)
    async with asyncio.timeout(5):
        await reading.wait()
    # Herdr saw the agent take up the new prompt; the next look finds it idle.
    watcher.follow(CONFIG, "wR:p2", second, target, working=True)
    agent.states = ["idle"]
    release.set()
    await settled(first, second)

    reports = [json.loads(text) for text in target.reports.values()]
    assert [[item["content"] for item in report["commands"]] for report in reports] == [
        ["先修滚动"],
        ["再补测试"],
    ]
    assert [report["outcome"] for report in reports] == ["finished", "finished"]
