"""Plugin setup is lazy and only authenticated task capture can originate work."""

import asyncio
import json

import pytest

from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.herdr.backend import agent_watch
from plugins.herdr.backend.cli import HerdrCli
from plugins.herdr.backend.plugin import setup
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from plugins.herdr.backend.service import TaskService


async def test_setup_uses_public_capabilities_without_starting_processes(tmp_path):
    context = FakeServiceContext("herdr", tmp_path)
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
    context = FakeServiceContext("herdr", tmp_path)
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
    first = FakeServiceContext("herdr", tmp_path)
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
    second = FakeServiceContext("herdr", tmp_path)
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
