"""Observable async task outcomes with controlled Herdr and delivery boundaries."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from contextvars import ContextVar
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.config import HerdrConfig
from plugins.herdr.backend.service import TaskService


class ScriptedCli(HerdrCli):
    """One explicit named-session script; no terminal or native agent starts."""

    def __init__(self, context, repository):
        super().__init__(HerdrConfig(), context.processes, repository)
        self.repository = repository
        self.calls = []
        self.prompt_error = None
        self.start_error = None
        self.state = "done"
        self.agent_kind = "codex"
        self.prompt_gate = asyncio.Event()
        self.prompt_gate.set()
        self.prompt_started = asyncio.Event()

    async def command(self, argv, **kwargs):
        if "status" in argv:
            return json.dumps(
                {
                    "running": True,
                    "version": "0.9.4",
                    "compatible": True,
                    "endpoint_compatible": True,
                }
            )
        if argv == ["herdr", "--version"]:
            return "herdr 0.9.4"
        if argv == ["git", "rev-parse", "--show-toplevel"]:
            return str(self.repository)
        if argv == ["git", "rev-parse", "HEAD"]:
            return "base-sha"
        raise AssertionError(argv)

    async def call(self, *args):
        self.calls.append(args)
        if args[:2] == ("worktree", "create"):
            path = args[args.index("--path") + 1]
            Path(path).mkdir(parents=True)
            return {
                "worktree": {"path": path, "branch": args[args.index("--branch") + 1]},
                "root_pane": {"pane_id": "w9:p1"},
                "workspace": {"workspace_id": "w9"},
            }
        if args[:2] == ("agent", "start"):
            if self.start_error:
                raise self.start_error
            return {"agent": {"agent_status": "idle"}}
        if args[:2] == ("agent", "prompt"):
            self.prompt_started.set()
            await self.prompt_gate.wait()
            if self.prompt_error:
                raise self.prompt_error
            return {"agent": {"agent_status": self.state}}
        if args[:2] == ("agent", "get"):
            return {
                "agent": {
                    "agent": self.agent_kind,
                    "pane_id": "w9:p1",
                    "agent_status": self.state,
                }
            }
        raise AssertionError(args)

    async def read(self, agent, *, source="recent-unwrapped"):
        return "terminal evidence"


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    context = FakeServiceContext("herdr", tmp_path)
    target = FakeBackgroundResultTarget("mira", "original-thread")
    cli = ScriptedCli(context, tmp_path)
    service = TaskService(tmp_path / "plugin-data")
    service.attach(context.process_resources, context.processes, tmp_path)
    monkeypatch.setattr(service, "create_cli", lambda config: cli)
    context.effect("service", service.close)
    return context, target, cli, service


@pytest.mark.parametrize("agent", ["codex", "claude"])
async def test_start_returns_before_execution_and_keeps_complete_requirement(
    fixture, agent
):
    context, target, cli, service = fixture
    cli.agent_kind = agent
    cli.prompt_gate.clear()
    requirement = "完整中文\n特殊字符：' \" ` $() &\n" + "长内容" * 10000
    task = service.start(str(cli.repository), requirement, agent, target, cli.config)
    assert task.status == "queued"
    await cli.prompt_started.wait()
    assert task.worker is not None and not task.worker.done()
    instructions = task.directory / f"{task.run_id}.md"
    assert instructions.read_text(encoding="utf-8").endswith(requirement)
    prompt = next(args[3] for args in cli.calls if args[:2] == ("agent", "prompt"))
    assert "\n" not in prompt and str(instructions).replace("\\", "\\\\") in prompt
    assert len(prompt) < 1000
    assert task.worktree != task.repository
    cli.prompt_gate.set()
    await task.worker
    assert task.status == "blocked"
    assert "结果文件" in task.error
    assert len(target.reports) == 1
    await context.aclose()


async def test_ambiguous_submission_is_never_resent_and_timeout_is_not_cancel(
    fixture, monkeypatch
):
    context, target, cli, service = fixture
    cli.prompt_error = CommandError("accepted possibly", code="timeout")
    cli.state = "unknown"
    ticks = iter([0, 1, 7201])
    monkeypatch.setattr(
        "plugins.herdr.backend.service.time",
        SimpleNamespace(monotonic=lambda: next(ticks)),
    )
    task = service.start(str(cli.repository), "fix", "codex", target, cli.config)
    await task.worker
    assert task.status == "unknown"
    assert "可能仍在运行" in task.error
    assert sum(args[:2] == ("agent", "prompt") for args in cli.calls) == 1
    assert not any("send-keys" in args or "close" in args for args in cli.calls)
    await context.aclose()


async def test_success_requires_delivery_verifier_and_reports_once(
    fixture, monkeypatch
):
    context, target, cli, service = fixture
    cli.prompt_gate.clear()
    task = service.start(str(cli.repository), "fix", "codex", target, cli.config)
    await cli.prompt_started.wait()
    task.result_path.write_text("{}", encoding="utf-8")
    verify = AsyncMock()
    monkeypatch.setattr("plugins.herdr.backend.service.verify_delivery", verify)
    cli.prompt_gate.set()
    await task.worker
    verify.assert_awaited_once_with(task, cli)
    assert task.status == "completed"
    assert json.loads(next(iter(target.reports.values())))["status"] == "completed"
    await context.aclose()


async def test_failed_delivery_and_agent_replacement_are_never_completed(
    fixture, monkeypatch
):
    context, target, cli, service = fixture
    cli.prompt_gate.clear()
    task = service.start(str(cli.repository), "fix", "codex", target, cli.config)
    await cli.prompt_started.wait()
    task.result_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "plugins.herdr.backend.service.verify_delivery",
        AsyncMock(side_effect=ValueError("PR 不存在")),
    )
    cli.prompt_gate.set()
    await task.worker
    assert task.status == "blocked" and "PR 不存在" in task.error
    cli.agent_kind = "claude"
    replacement = service.start(str(cli.repository), "fix", "codex", target, cli.config)
    await replacement.worker
    assert replacement.status == "blocked" and "替换" in replacement.error
    await context.aclose()


async def test_startup_blocked_preserves_terminal_and_never_submits_requirement(
    fixture,
):
    context, target, cli, service = fixture
    cli.start_error = CommandError("not ready", code="agent_not_ready")
    task = service.start(str(cli.repository), "fix", "codex", target, cli.config)
    await task.worker
    assert task.status == "blocked" and task.agent_state == "blocked"
    assert "terminal evidence" in task.error
    assert task.pane_id == "w9:p1"
    assert not any(args[:2] == ("agent", "prompt") for args in cli.calls)
    await context.aclose()


@pytest.mark.parametrize(
    "agent, flag",
    [
        ("codex", "--dangerously-bypass-approvals-and-sandbox"),
        ("claude", "--dangerously-skip-permissions"),
    ],
)
async def test_selected_agent_model_and_full_access_reach_native_start(
    fixture, agent, flag
):
    context, target, cli, service = fixture
    cli.agent_kind = agent
    cli.config = HerdrConfig(codex_model="codex-test", claude_model="claude-test")
    task = service.start(str(cli.repository), "fix", agent, target, cli.config)
    await task.worker
    start = next(args for args in cli.calls if args[:2] == ("agent", "start"))
    assert start[start.index("--kind") + 1] == agent
    assert start[start.index("--") + 1 :] == (flag, "--model", f"{agent}-test")
    await context.aclose()


async def test_working_read_uses_visible_and_read_race_does_not_abandon_task(
    fixture, monkeypatch
):
    context, target, cli, service = fixture
    cli.prompt_gate.clear()
    cli.prompt_error = CommandError("wait timeout", code="timeout")
    cli.state = "working"
    task = service.start(str(cli.repository), "fix", "codex", target, cli.config)
    await cli.prompt_started.wait()
    reads = []

    async def read(agent, *, source):
        reads.append(source)
        if len(reads) == 1:
            cli.state = "done"
            task.result_path.write_text("{}", encoding="utf-8")
            raise CommandError(
                "alternate screen history unavailable", code="invalid_state"
            )
        return "done"

    monkeypatch.setattr(cli, "read", read)
    monkeypatch.setattr("plugins.herdr.backend.service.verify_delivery", AsyncMock())
    cli.prompt_gate.set()
    await task.worker
    assert reads == ["visible", "recent-unwrapped"]
    assert task.status == "completed"
    await context.aclose()


async def test_monitor_does_not_inherit_runtime_context_and_keeps_config_snapshot(
    fixture, monkeypatch
):
    context, target, cli, service = fixture
    inherited = ContextVar("runtime-marker", default="none")
    inherited.set("retiring-generation")
    seen = []
    started, finish = asyncio.Event(), asyncio.Event()

    async def execute(task, *, continuing=False):
        seen.append(inherited.get())
        started.set()
        try:
            await finish.wait()
        except asyncio.CancelledError:
            task.touch("monitoring_stopped")
            raise

    monkeypatch.setattr(service, "_execute", execute)
    config = HerdrConfig(session="original")
    task = service.start(str(cli.repository), "fix", "codex", target, config)
    config.session = "different"
    await started.wait()
    assert seen == ["none"] and task.config.session == "original"
    await service.close()
    assert task.status == "monitoring_stopped" and not target.reports
    assert not cli.calls
    await context.aclose()


async def test_close_before_monitor_first_runs_marks_stopped_without_native_calls(
    fixture,
):
    context, target, cli, service = fixture
    task = service.start(str(cli.repository), "fix", "codex", target, cli.config)
    await service.close()
    assert task.status == "monitoring_stopped"
    assert not cli.calls and not target.reports
    await context.aclose()
