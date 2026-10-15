"""Session agent RPC: workspace grouping, task links and session availability."""

import json

import pytest

from plugins.herdr.backend.agents import SessionAgents
from plugins.herdr.backend.cli import CommandError
from plugins.herdr.backend.config import HerdrConfig
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from shiori_sdk.rpc import Concurrency
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.service_context import FakeServiceContext


def agent(pane_id, workspace_id, kind="claude", status="working", title="标题"):
    """An entry shaped like Herdr 0.9.5 `agent list` output."""
    return {
        "agent": kind,
        "agent_status": status,
        "cwd": "D:\\Coding\\Shiori",
        "focused": False,
        "pane_id": pane_id,
        "tab_id": f"{workspace_id}:t1",
        "terminal_id": "term_x",
        "terminal_title": f"◐ {title}",
        "terminal_title_stripped": title,
        "workspace_id": workspace_id,
    }


class ScriptedHerdr:
    """Answers argv like the Herdr CLI and records each command."""

    def __init__(self):
        self.argv: list[list[str]] = []
        self.running = True
        self.agents = [
            agent("wR:p2", "wR", title="herdr插件问题"),
            agent("w9:p1", "w9", kind="codex", status="idle"),
            agent("wR:p4", "wR", status="done"),
        ]
        self.workspaces = [
            {"workspace_id": "w9", "label": "shiori-task", "number": 3},
            {"workspace_id": "wR", "label": "Shiori", "number": 2},
            {"workspace_id": "wE", "label": "空", "number": 1},
        ]

    async def command(self, argv, **_kwargs):
        self.argv.append(argv)
        if argv[1:] == ["--version"]:
            return "herdr 0.9.5"
        if argv[-3:] == ["status", "server", "--json"]:
            status = {"running": self.running}
            if self.running:
                status |= {
                    "version": "0.9.5",
                    "compatible": True,
                    "endpoint_compatible": True,
                }
            return json.dumps(status)
        if not self.running:
            # The CLI's answer once the session's server has gone away.
            raise CommandError("no herdr server", code="server_not_running")
        if argv[3:] == ["agent", "list"]:
            return json.dumps({"result": {"agents": self.agents}})
        if argv[3:] == ["workspace", "list"]:
            return json.dumps({"result": {"workspaces": self.workspaces}})
        if argv[3:5] == ["agent", "get"]:
            found = [item for item in self.agents if item["pane_id"] == argv[5]]
            if not found:
                return json.dumps(
                    {"error": {"code": "agent_not_found", "message": "x"}}
                )
            return json.dumps({"result": {"agent": found[0]}})
        if argv[3:5] == ["agent", "read"]:
            return f"output of {argv[5]} via {argv[7]}"
        raise AssertionError(argv)


def make_task(tmp_path, task_id, *, pane_id, session="default", created_at="t1"):
    task = CodingTask(
        task_id,
        "修复滚动",
        tmp_path,
        "codex",
        FakeBackgroundResultTarget("role-a", "thread"),
        tmp_path,
        "branch",
        "run",
        config=HerdrConfig(session=session),
        pane_id=pane_id,
    )
    task.created_at = created_at
    return task


@pytest.fixture
def fixture(tmp_path):
    ctx = FakeServiceContext("herdr", tmp_path)
    service = TaskService(tmp_path, ctx.processes)
    view = SessionAgents(
        service, ctx.as_capability(), HerdrConfig(session="default"), tmp_path
    )
    herdr = ScriptedHerdr()
    view.cli.command = herdr.command  # type: ignore[method-assign]
    view.register()
    return ctx, service, herdr


async def test_agents_are_grouped_by_workspace_and_linked_to_their_task(
    fixture, tmp_path
):
    ctx, service, herdr = fixture
    for name in ("agents.list", "agents.get"):
        assert ctx.rpc.concurrency[name] is Concurrency.READ_ONLY
    # Same pane: the older task and a task of another session are not linked.
    for task in (
        make_task(tmp_path, "old", pane_id="w9:p1", created_at="t0"),
        make_task(tmp_path, "new", pane_id="w9:p1", created_at="t2"),
        make_task(tmp_path, "elsewhere", pane_id="wR:p2", session="other"),
    ):
        service.tasks[task.id] = task

    listed = await ctx.rpc.handlers["agents.list"]({})

    assert listed["session"] == "default"
    assert [
        (group["label"], [item["pane_id"] for item in group["agents"]])
        for group in listed["workspaces"]
    ] == [("Shiori", ["wR:p2", "wR:p4"]), ("shiori-task", ["w9:p1"])]
    first = listed["workspaces"][0]["agents"][0]
    assert first == {
        "pane_id": "wR:p2",
        "workspace_id": "wR",
        "agent": "claude",
        "status": "working",
        "title": "herdr插件问题",
        "cwd": "D:\\Coding\\Shiori",
        "task_id": None,
    }
    assert listed["workspaces"][1]["agents"][0]["task_id"] == "new"
    assert all(argv[1:3] == ["--session", "default"] for argv in herdr.argv[1:])
    await ctx.aclose()


async def test_get_reads_the_agent_and_its_task_and_reports_a_gone_agent(
    fixture, tmp_path
):
    ctx, service, herdr = fixture
    service.tasks["new"] = make_task(tmp_path, "new", pane_id="w9:p1")

    detail = await ctx.rpc.handlers["agents.get"]({"pane_id": "w9:p1"})
    assert detail["agent"]["status"] == "idle"
    assert detail["output"] == "output of w9:p1 via recent-unwrapped"
    assert detail["task"]["id"] == "new"
    assert detail["task"]["can_cancel"] is True

    working = await ctx.rpc.handlers["agents.get"]({"pane_id": "wR:p2"})
    assert working["output"] == "output of wR:p2 via visible"
    assert working["task"] is None

    herdr.agents = []
    gone = await ctx.rpc.handlers["agents.get"]({"pane_id": "w9:p1"})
    assert gone == {"session": "default", "agent": None, "output": "", "task": None}
    await ctx.aclose()


async def test_session_is_checked_once_and_again_after_it_becomes_unavailable(
    fixture,
):
    ctx, _service, herdr = fixture
    list_agents = ctx.rpc.handlers["agents.list"]
    await list_agents({})
    await list_agents({})
    assert sum(argv[1:] == ["--version"] for argv in herdr.argv) == 1

    herdr.running = False
    with pytest.raises(CommandError, match="no herdr server"):
        await list_agents({})
    # The failed read invalidates the check, so the next poll names the reason.
    with pytest.raises(CommandError, match="session 'default' 未运行"):
        await list_agents({})
    herdr.running = True
    assert (await list_agents({}))["workspaces"]

    ctx.process_resources.active = False
    with pytest.raises(RuntimeError, match="配置已替换"):
        await list_agents({})
    await ctx.aclose()
