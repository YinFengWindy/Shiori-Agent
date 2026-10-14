"""Real app generations retain plugin resources across independent import namespaces."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures


async def test_app_reload_discard_disable_and_shutdown_own_resource_lifetime(
    tmp_path, monkeypatch
):
    plugin = tmp_path / "packages" / "resource_probe"
    (plugin / "backend").mkdir(parents=True)
    (plugin / "manifest.yaml").write_text(
        "api: 2\nid: resource_probe\ncapabilities: [process_resources]\n",
        encoding="utf-8",
    )
    (plugin / "backend" / "plugin.py").write_text(
        """class Resource:
    def __init__(self):
        self.closed = 0
        self.records = ["original task"]
    async def close(self):
        self.closed += 1

async def setup(ctx):
    resource = ctx.process_resources.acquire("tasks-v1", Resource)
    ctx.expose(resource)
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [plugin.parent]
    )
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path / "workspace",
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    resource = app.core.plugin_manager._dependency_api("resource_probe")
    old = app.core
    try:
        discarded = await app.prepare(replace(config, max_tokens=2048))
        assert (
            discarded.core.plugin_manager._dependency_api("resource_probe") is resource
        )
        await app.discard(discarded)
        assert resource.closed == 0
        candidate = await app.prepare(replace(config, max_tokens=3072))
        await app.publish(candidate)
        assert app.core.plugin_manager._dependency_api("resource_probe") is resource
        await asyncio.sleep(0)
        assert resource.records == ["original task"] and resource.closed == 0
        assert old is not app.core
        disabled = await app.prepare(
            replace(app.config, plugins={"resource_probe": {"enabled": False}})
        )
        await app.publish(disabled)
        assert resource.closed == 1
    finally:
        await app.shutdown()
    assert resource.closed == 1


async def test_post_publish_cleanup_error_keeps_committed_generation_and_is_reported(
    tmp_path, monkeypatch, caplog
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
    candidate = await app.prepare(replace(config, max_tokens=2048))
    error = ExceptionGroup("resource cleanup", [ValueError("cannot close resource")])
    with monkeypatch.context() as patch:
        patch.setattr(
            app._plugin_process_resources, "drain", AsyncMock(side_effect=error)
        )
        await app.publish(candidate)
    assert app.generation == 2 and candidate.published
    assert app.config.max_tokens == 2048 and app.core is candidate.core
    assert app._cleanup_errors == [error]
    assert "Published plugin resource cleanup failed" in caplog.text
    with pytest.raises(ExceptionGroup):
        await app.shutdown()
    assert app.http_resources._closed
