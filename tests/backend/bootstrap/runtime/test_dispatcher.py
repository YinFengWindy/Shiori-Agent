"""Background result turns select the published generation at delivery time."""

from dataclasses import replace
from unittest.mock import AsyncMock

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures


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
