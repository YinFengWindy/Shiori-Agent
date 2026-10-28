"""Plugin setup is lazy and only authenticated task capture can originate work."""

import asyncio
import json
from pathlib import Path

import pytest

from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.herdr.backend import agent_watch
from plugins.herdr.backend.cli import HerdrCli
from plugins.herdr.backend.plugin import setup
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from plugins.herdr.backend.service import TaskService

PACKAGE_DIR = Path(__file__).resolve().parents[1]


async def test_setup_uses_public_capabilities_without_starting_processes(tmp_path):
    context = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    await setup(context.as_capability())
    assert isinstance(context.exported, TaskService)
    assert context.exported.tasks == {}
    tool = context.tools.tools["herdr_start_task"]
    with pytest.raises(PermissionError):
        await tool.execute(
            repository=str(tmp_path), requirement="fix", role_id="forged"
        )
    assert context.exported.tasks == {}
    await context.aclose()


async def test_agent_tools_run_without_confirmation_and_declare_their_effect(
    tmp_path,
):
    context = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    await setup(context.as_capability())
    risks = {
        name: context.tools.options[name]["risk"]
        for name in (
            "herdr_list_agents",
            "herdr_read_agent",
            "herdr_prompt_agent",
            "herdr_send_keys",
        )
    }
    assert risks == {
        "herdr_list_agents": "read-only",
        "herdr_read_agent": "read-only",
        "herdr_prompt_agent": "external-side-effect",
        "herdr_send_keys": "external-side-effect",
    }
    for name in risks:
        description = context.tools.tools[name].description
        assert "herdr_start_task" in description and "shell" in description
    await context.aclose()


class Generation:
    """One generation's attachment to the process's resources, published or not."""

    def __init__(self, shared: dict[str, object]):
        self.active = True
        self.shared = shared

    def acquire(self, key, factory):
        if key not in self.shared:
            self.shared[key] = factory()
        return self.shared[key]


async def test_a_watch_continues_on_the_generation_published_after_a_reload(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(agent_watch, "POLL_SECONDS", 0)
    state = {"agent_status": "working"}
    revoked: list[object] = []

    async def command(cli, argv, **_kwargs):
        if any(cli.processes is processes for processes in revoked):
            raise RuntimeError("已撤销的 generation 能力")
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
        if argv[3:5] == ["agent", "read"]:
            return "done"
        return json.dumps({"result": {"agent": {**state, "pane_id": "wR:p2"}}})

    monkeypatch.setattr(HerdrCli, "command", command)
    shared: dict[str, object] = {}
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    first = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    first.process_resources = Generation(shared)  # type: ignore[assignment]
    first.tools.context = {"role_id": "role-a"}
    first.background_results.target = target
    await setup(first.as_capability())
    sent = json.loads(
        await first.tools.tools["herdr_prompt_agent"].execute(
            pane_id="wR:p2", text="修滚动"
        )
    )
    assert sent["ok"] is True

    # The reload publishes a second generation and retires the first.
    first.process_resources.active = False
    revoked.append(first.processes)
    second = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    second.process_resources = Generation(shared)  # type: ignore[assignment]
    await setup(second.as_capability())
    state["agent_status"] = "idle"
    try:
        async with asyncio.timeout(5):
            while not target.reports:
                await asyncio.sleep(0)
        [text] = target.reports.values()
        assert json.loads(text)["outcome"] == "finished"
    finally:
        for resource in shared.values():
            await resource.close()  # type: ignore[attr-defined]
        await first.aclose()
        await second.aclose()


async def test_a_task_is_monitored_and_verified_on_the_generation_published_after_a_reload(
    tmp_path, monkeypatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    revoked: list[object] = []
    prompted, release = asyncio.Event(), asyncio.Event()
    state = {"agent_status": "working"}
    branch = {}

    async def command(cli, argv, *, cwd=None, timeout=None):
        if any(cli.processes is processes for processes in revoked):
            raise RuntimeError("已撤销的 generation 能力")
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
        if argv[0] == "git":
            if argv[1:] == ["branch", "--show-current"]:
                return branch["name"]
            return {
                ("rev-parse", "--show-toplevel"): str(repository),
                ("rev-parse", "HEAD"): (
                    "base-sha" if cwd == repository.resolve() else "head-sha"
                ),
                ("status", "--porcelain"): "",
                ("diff", "--name-only", "base-sha", "HEAD"): "fix.py",
            }[tuple(argv[1:])]
        if argv[0] == "gh":
            return json.dumps(
                {
                    "url": "https://github.com/o/r/pull/1",
                    "isDraft": True,
                    "state": "OPEN",
                    "headRefName": branch["name"],
                    "headRefOid": "head-sha",
                    "baseRefName": "main",
                }
            )
        if argv == ["pytest"]:
            return "passed"
        args = argv[3:]
        if args[:2] == ["worktree", "create"]:
            path = args[args.index("--path") + 1]
            Path(path).mkdir(parents=True)
            branch["name"] = args[args.index("--branch") + 1]
            return json.dumps(
                {
                    "result": {
                        "worktree": {"path": path, "branch": branch["name"]},
                        "root_pane": {"pane_id": "w9:p1"},
                        "workspace": {"workspace_id": "w9"},
                    }
                }
            )
        if args[:2] == ["agent", "read"]:
            return "done"
        if args[:2] == ["agent", "prompt"]:
            # Accepted by the first generation, which retires meanwhile.
            prompted.set()
            await release.wait()
        agent = {**state, "agent": "codex", "pane_id": "w9:p1"}
        return json.dumps({"result": {"agent": agent}})

    monkeypatch.setattr(HerdrCli, "command", command)
    shared: dict[str, object] = {}
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    first = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    first.process_resources = Generation(shared)  # type: ignore[assignment]
    first.tools.context = {"role_id": "role-a"}
    first.background_results.target = target
    await setup(first.as_capability())
    service = first.exported
    assert isinstance(service, TaskService)
    started = json.loads(
        await first.tools.tools["herdr_start_task"].execute(
            repository=str(repository), requirement="修滚动"
        )
    )
    second = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    try:
        [task] = service.tasks.values()
        assert task.id == started["task_id"] and task.worker is not None
        await asyncio.wait(
            [asyncio.ensure_future(prompted.wait()), task.worker],
            timeout=5,
            return_when=asyncio.FIRST_COMPLETED,
        )
        assert prompted.is_set(), task.error

        # The reload publishes a second generation and retires the first.
        first.process_resources.active = False
        revoked.append(first.processes)
        second.process_resources = Generation(shared)  # type: ignore[assignment]
        await setup(second.as_capability())
        assert second.exported is service
        state["agent_status"] = "idle"
        task.result_path.write_text(
            json.dumps(
                {
                    "task_id": task.id,
                    "run_id": task.run_id,
                    "status": "completed",
                    "summary": "修好了",
                    "validation": [{"argv": ["pytest"]}],
                    "pr_url": "https://github.com/o/r/pull/1",
                }
            ),
            encoding="utf-8",
        )
        release.set()
        async with asyncio.timeout(5):
            while not target.reports:
                await asyncio.sleep(0)
        assert task.status == "completed", task.error
        assert task.pr_url == "https://github.com/o/r/pull/1"
        assert task.validation[0]["output"] == "passed"
        [text] = target.reports.values()
        assert json.loads(text)["status"] == "completed"
    finally:
        release.set()
        for resource in shared.values():
            await resource.close()  # type: ignore[attr-defined]
        await first.aclose()
        await second.aclose()
