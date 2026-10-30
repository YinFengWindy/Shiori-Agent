"""The plugin's setup: one process loop across generations, stopped with the plugin."""

from __future__ import annotations

import asyncio
from pathlib import Path

from shiori_sdk.core.markdown_memory import MARKDOWN_MEMORY
from shiori_sdk.core.memory_optimizer import MEMORY_OPTIMIZER
from shiori_sdk.core.models import MAIN_MODEL
from shiori_sdk.core.services import PROCESS_RESOURCES
from shiori_sdk.testing.process_resources import FakeProcessResources
from shiori_sdk.testing.service_context import FakeServiceContext

from plugins.memory_optimizer.backend.plugin import setup

from .conftest import FakeMarkdownMemory, FakeRoleDocuments, HeldProvider, Snapshot

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def _context(
    workspace: Path,
    memory: FakeMarkdownMemory,
    provider: HeldProvider,
    resources: FakeProcessResources | None = None,
) -> FakeServiceContext:
    """One generation of the plugin; ``resources`` stands for the process."""
    ctx = FakeServiceContext("memory_optimizer", workspace, package_dir=PACKAGE_DIR)
    ctx.serve(MARKDOWN_MEMORY, memory)
    ctx.serve(MAIN_MODEL, "chat-model")
    if resources is not None:
        ctx.serve(PROCESS_RESOURCES, resources)
    ctx.fake_roles.create_role(role_id="mira", name="mira", system_prompt="")
    ctx.fake_models.snapshots["mira", "chat"] = Snapshot(provider, "chat-model")
    return ctx


def _loops() -> list[asyncio.Task[object]]:
    return [
        task
        for task in asyncio.all_tasks()
        if task.get_name() == "memory_optimizer:loop" and not task.done()
    ]


def _overdue_role() -> FakeRoleDocuments:
    """Never optimized, so the loop's start optimizes it at once."""
    return FakeRoleDocuments(
        long_term="# 我的长期记忆\n- 旧", pending="- [identity] 新"
    )


async def test_generations_share_one_loop(tmp_path: Path) -> None:
    memory = FakeMarkdownMemory()
    process = FakeProcessResources()
    old = _context(tmp_path, memory, HeldProvider(), process)
    new = _context(tmp_path, memory, HeldProvider(), process)
    try:
        await setup(old)
        await setup(new)
        assert len(_loops()) == 1

        await old.aclose()
        assert len(_loops()) == 1
        assert new.kernel.get(MEMORY_OPTIMIZER) is not None
    finally:
        await new.aclose()
        await process.close()
    assert _loops() == []


async def test_disabling_cancels_the_running_optimization(tmp_path: Path) -> None:
    memory = FakeMarkdownMemory()
    documents = memory.roles["mira"] = _overdue_role()
    provider = HeldProvider("merged")
    provider.hold = asyncio.Event()
    ctx = _context(tmp_path, memory, provider)
    await setup(ctx)
    await asyncio.wait_for(provider.started.wait(), timeout=5)
    run = ctx.kernel.get(MEMORY_OPTIMIZER).active_run()
    assert run is not None and run.role_id == "mira"

    # Disabling closes the plugin scope and with it the process resource.
    await ctx.aclose()

    assert provider.cancelled
    assert _loops() == []
    assert documents.pending == "- [identity] 新"
    assert documents.commits == 0


async def test_a_run_on_a_retired_generation_reruns_on_the_current_one(
    tmp_path: Path,
) -> None:
    memory = FakeMarkdownMemory()
    documents = memory.roles["mira"] = _overdue_role()
    old_provider = HeldProvider()
    old_provider.hold = asyncio.Event()
    new_provider = HeldProvider("# 我的长期记忆\n- 新")
    process = FakeProcessResources()
    old = _context(tmp_path, memory, old_provider, process)
    new = _context(tmp_path, memory, new_provider, process)
    try:
        await setup(old)
        await asyncio.wait_for(old_provider.started.wait(), timeout=5)
        await setup(new)

        await old.aclose()
        await asyncio.wait_for(new_provider.started.wait(), timeout=5)
        for _ in range(100):
            if documents.commits:
                break
            await asyncio.sleep(0.01)

        assert old_provider.cancelled
        assert documents.rollbacks == 1
        assert documents.commits == 1
        assert documents.long_term == "# 我的长期记忆\n- 新"
    finally:
        await new.aclose()
        await process.close()
