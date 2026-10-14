"""Continuation ownership and cancellation confirmation against controlled agents."""

import asyncio
from types import SimpleNamespace

import pytest

from plugins.herdr.backend.cli import HerdrCli
from plugins.herdr.backend.config import HerdrConfig
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from plugins.herdr.backend.task_management import (
    cancel_task,
    continue_task,
    owned_task,
    task_snapshot,
    inspect_task,
)
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.processes import FakeProcesses


class AgentCli(HerdrCli):
    def __init__(self, directory):
        super().__init__(HerdrConfig(session="original"), FakeProcesses(), directory)
        self.calls = []
        self.status = "idle"
        self.kind = "codex"
        self.stops = True

    async def call(self, *args):
        self.calls.append(args)
        if args[:2] == ("agent", "get"):
            return {
                "agent": {
                    "agent": self.kind,
                    "agent_status": self.status,
                    "pane_id": "owned-pane",
                }
            }
        if args[:2] == ("agent", "send-keys"):
            if self.stops:
                self.status = "idle"
            return {}
        raise AssertionError(args)

    async def read(self, agent, *, source="recent-unwrapped"):
        return "needs interaction"


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    service = TaskService(tmp_path, FakeProcesses())
    task = CodingTask(
        "task-a",
        "original",
        tmp_path,
        "codex",
        target,
        tmp_path,
        "codex/task",
        "run-a",
        worktree=tmp_path,
        pane_id="owned-pane",
        agent_name="owned-agent",
        status="blocked",
        config=HerdrConfig(session="original"),
    )
    service.tasks[task.id] = task
    cli = AgentCli(tmp_path)
    configurations = []

    def create_cli(config):
        configurations.append(config.session)
        return cli

    monkeypatch.setattr(service, "create_cli", create_cli)
    return service, task, cli, target, configurations


async def test_continue_reuses_agent_and_worktree_with_new_run_and_no_concurrent_submit(
    fixture, monkeypatch
):
    service, task, cli, target, configurations = fixture
    started, finish = asyncio.Event(), asyncio.Event()

    async def execute(current, *, continuing):
        assert current is task and continuing
        started.set()
        await finish.wait()

    monkeypatch.setattr(service, "_execute", execute)
    old_run, worktree = task.run_id, task.worktree
    assert await continue_task(service, task.id, "新要求\n第二行", "role-a") is task
    await started.wait()
    assert task.run_id != old_run and task.worktree == worktree
    assert task.agent_name == "owned-agent" and configurations == ["original"]
    assert task.requirement.endswith("新要求\n第二行")
    with pytest.raises(ValueError, match="仍在执行"):
        await continue_task(service, task.id, "并发", "role-a")
    assert cli.calls == [("agent", "get", "owned-agent")]
    finish.set()
    await task.worker


@pytest.mark.parametrize("operation", ["read", "continue", "cancel"])
async def test_other_role_cannot_observe_or_operate_task(fixture, operation):
    service, task, cli, target, _ = fixture
    with pytest.raises(ValueError, match="当前角色"):
        if operation == "read":
            owned_task(service, task.id, "role-b")
        elif operation == "continue":
            await continue_task(service, task.id, "new", "role-b")
        else:
            await cancel_task(service, task.id, "role-b")
    assert not cli.calls and not target.reports


@pytest.mark.parametrize("status", ["working", "blocked", "unknown"])
async def test_continue_does_not_answer_unrecognized_interaction_or_interrupt_work(
    fixture, status
):
    service, task, cli, _, _ = fixture
    cli.status = status
    with pytest.raises(ValueError, match="尚未准备"):
        await continue_task(service, task.id, "new", "role-a")
    assert task.run_id == "run-a"
    assert not any("prompt" in call or "send-keys" in call for call in cli.calls)


@pytest.mark.parametrize("agent", ["codex", "claude"])
async def test_cancel_reports_only_after_agent_stops_and_preserves_worktree(
    fixture, agent
):
    service, task, cli, target, _ = fixture
    cli.kind = task.agent = agent
    cli.status = "working"
    task.prompt_sent = True
    task.status = "running"
    path = task.worktree / "artifact.txt"
    path.write_text("keep me", encoding="utf-8")
    task.worker = asyncio.create_task(asyncio.Event().wait())
    await cancel_task(service, task.id, "role-a")
    assert task.status == "cancelling" and not target.reports
    repeated = await cancel_task(service, task.id, "role-a")
    assert repeated is task
    await task.worker
    assert task.status == "cancelled"
    assert path.read_text(encoding="utf-8") == "keep me"
    assert len(target.reports) == 1
    assert sum("send-keys" in call for call in cli.calls) == 1
    assert task_snapshot(task)["worktree"] == str(task.worktree)


async def test_cancel_timeout_stays_unknown_and_never_kills_server(
    fixture, monkeypatch
):
    service, task, cli, target, _ = fixture
    cli.status, cli.stops = "working", False
    ticks = iter([0, 999])
    monkeypatch.setattr(
        "plugins.herdr.backend.task_management.time",
        SimpleNamespace(monotonic=lambda: next(ticks)),
    )
    await cancel_task(service, task.id, "role-a")
    await task.worker
    assert task.status == "unknown" and "未确认停止" in task.error
    assert not any("server" in call or "remove" in call for call in cli.calls)


async def test_completed_result_wins_over_late_cancel(fixture):
    service, task, cli, target, _ = fixture
    task.status = "completed"
    assert await cancel_task(service, task.id, "role-a") is task
    assert task.status == "completed" and not cli.calls and not target.reports


async def test_inspect_refreshes_output_without_claiming_delivery_or_resubmitting(
    fixture,
):
    service, task, cli, target, _ = fixture
    task.status = "unknown"
    cli.status = "done"
    assert await inspect_task(service, task.id, "role-a") is task
    assert task.agent_state == "done" and task.output == "needs interaction"
    assert task.status == "unknown" and not target.reports
    assert cli.calls == [("agent", "get", "owned-agent")]


async def test_disable_during_continue_read_cannot_launch_a_new_run(
    fixture, monkeypatch
):
    service, task, cli, _, _ = fixture
    original = cli.call

    async def close_during_read(*args):
        await service.close()
        return await original(*args)

    monkeypatch.setattr(cli, "call", close_during_read)
    with pytest.raises(RuntimeError, match="停止追踪"):
        await continue_task(service, task.id, "new", "role-a")
    assert task.run_id == "run-a" and task.worker is None
