"""Background result turns select the published generation at delivery time."""

from dataclasses import replace
from unittest.mock import AsyncMock
import asyncio
from types import SimpleNamespace
import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures
from bootstrap.runtime.dispatcher import RuntimeDispatcher
from bootstrap.runtime.generations import RuntimeCandidate
from bus.queue import MessageBus
from shiori_sdk.messages import InboundMessage


async def test_background_result_runs_on_new_loop_and_releases_short_lease(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    old_loop = app.core.loop
    old_runner = AsyncMock()
    monkeypatch.setattr(old_loop, "process_background_result", old_runner)
    saved_runner = app._dispatcher.process_background_result
    candidate = await app.prepare(replace(config, max_tokens=2048))
    current_runner = AsyncMock()
    monkeypatch.setattr(
        candidate.core.loop, "process_background_result", current_runner
    )
    await app.publish(candidate)
    try:
        context, admission = object(), lambda: None
        await saved_runner(context, admission)
        current_runner.assert_awaited_once_with(context, admission)
        old_runner.assert_not_called()
        assert candidate.references == 0
    finally:
        await app.shutdown()


async def test_chat_lanes_preserve_order_and_release_accepted_leases_on_shutdown():
    bus = MessageBus()
    entered, other_done, release = (asyncio.Event() for _ in range(3))
    seen = []

    async def process(item):
        seen.append(item.content)
        if item.content == "a1":
            entered.set()
            await release.wait()
        if item.content == "b1":
            other_done.set()

    candidate = RuntimeCandidate(
        1,
        SimpleNamespace(loop=SimpleNamespace(process_inbound=process)),
        SimpleNamespace(),
    )
    app = SimpleNamespace(
        bus=bus, wait_for_admission=AsyncMock(), acquire=candidate.acquire
    )
    bus.bind_runtime_admission(candidate.acquire)
    for chat, content in (("a", "a1"), ("a", "a2"), ("b", "b1")):
        await bus.publish_inbound(
            InboundMessage(
                "qqbot",
                "user",
                chat,
                content,
                metadata={"session_key_override": "role:mira"},
            )
        )
    task = asyncio.create_task(RuntimeDispatcher(app).run())
    await asyncio.wait_for(entered.wait(), 1)
    await asyncio.wait_for(other_done.wait(), 1)
    assert seen == ["a1", "b1"]
    assert candidate.references == 2
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert candidate.references == 0
    assert seen == ["a1", "b1"]
