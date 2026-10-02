"""Host assembly and storage initialization select exactly one memory engine."""

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from agent.config_models import Config, MemoryConfig
from agent.provider import LLMProvider
from agent.tools.registry import ToolRegistry
from bootstrap.memory import build_memory_runtime, ensure_memory_plugin_storage
from bootstrap.paths import REPOSITORY_ROOT
from core.memory.engine import (
    MemoryCapability,
)
from core.memory.plugin import MemoryPluginRuntime
from core.net.http import HttpRequester, SharedHttpResources
from session.store import SessionStore


@pytest.mark.asyncio
async def test_default_engine_assembles_without_model_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    plugin_root = tmp_path / "plugins"
    package = "default_memory"
    backend = plugin_root / package / "backend"
    _ = shutil.copytree(
        REPOSITORY_ROOT / "plugins" / package / "backend",
        backend,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    _ = (backend / "config.local.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr("bootstrap.memory_plugins.plugin_roots", lambda: [plugin_root])
    monkeypatch.setitem(sys.modules, "plugins", None)
    monkeypatch.chdir(tmp_path)
    request = AsyncMock(side_effect=AssertionError("assembly must not request models"))
    monkeypatch.setattr(HttpRequester, "request", request)
    provider = Mock(spec=LLMProvider)
    provider.chat = AsyncMock(side_effect=AssertionError("assembly must not chat"))
    config = Config(provider="openai", model="test", api_key="test")
    config.memory.enabled = True
    config.memory.engine = "default"
    workspace = tmp_path / "workspace"
    selected_db = workspace / "plugin-data" / package / "memory2.db"

    storage = ensure_memory_plugin_storage(config, workspace)
    assert storage == [(selected_db, False)]
    assert selected_db.is_file()
    assert ensure_memory_plugin_storage(config, workspace) == [(selected_db, True)]
    # Normal host startup creates the conversation store before memory runtime.
    sessions = SessionStore(workspace / "sessions.db")
    sessions.close()

    http = SharedHttpResources()
    try:
        runtime = build_memory_runtime(
            config, workspace, ToolRegistry(), provider, None, http
        )
        try:
            assert runtime.engine.describe().name == "default"
            assert len(runtime.resources) == 2
            engine_file = sys.modules[type(runtime.engine).__module__].__file__
            assert engine_file is not None
            assert Path(engine_file).is_relative_to(backend)
            request.assert_not_called()
            provider.chat.assert_not_called()
            assert capsys.readouterr().out == ""
        finally:
            await runtime.aclose()
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_disabled_memory_does_not_resolve_or_initialize_an_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def unexpected_resolve(_name: str):
        raise AssertionError("disabled memory must not load an engine")

    monkeypatch.setattr("bootstrap.wiring.resolve_memory_plugin", unexpected_resolve)
    config = Config(provider="openai", model="test", api_key="test")
    config.memory.enabled = False
    assert ensure_memory_plugin_storage(config, tmp_path) == []
    http = SharedHttpResources()
    try:
        runtime = build_memory_runtime(
            config, tmp_path, ToolRegistry(), Mock(spec=LLMProvider), None, http
        )
        assert runtime.engine.describe().name == "disabled"
        assert runtime.closeables == []
    finally:
        await http.aclose()


def test_retired_engine_in_source_layout_fails_without_creating_data(tmp_path):
    config = Config(provider="openai", model="test", api_key="test")
    config.memory.engine = "akasha"
    config.memory.enabled = True
    with pytest.raises(ValueError, match="未知 memory engine: akasha"):
        ensure_memory_plugin_storage(config, tmp_path)
    assert not (tmp_path / "plugin-data").exists()


def test_build_memory_runtime_uses_memory_plugin(monkeypatch, tmp_path: Path):
    import bootstrap.memory as memory_module

    monkeypatch.setattr(
        memory_module,
        "register_memory_meta_tools",
        lambda *args, **kwargs: None,
    )

    captured: dict[str, object] = {}

    class _CustomEngine:
        def describe(self):
            return SimpleNamespace(name="custom")

    class _CustomPlugin:
        plugin_id = "custom"

        def build(self, deps):
            captured["deps"] = deps
            return MemoryPluginRuntime(engine=cast(Any, _CustomEngine()))

    monkeypatch.setattr(
        "bootstrap.wiring.resolve_memory_plugin",
        lambda name: _CustomPlugin(),
    )

    runtime = build_memory_runtime(
        config=Config(
            provider="test",
            model="gpt-test",
            api_key="k",
            memory=MemoryConfig(enabled=True, engine="custom"),
        ),
        workspace=tmp_path,
        tools=ToolRegistry(),
        provider=cast(Any, SimpleNamespace()),
        light_provider=None,
        http_resources=cast(Any, SimpleNamespace(external_default=SimpleNamespace())),
    )

    assert runtime.engine is not None
    assert runtime.engine.describe().name == "custom"
    deps = captured["deps"]
    assert deps.config.model == "gpt-test"
    assert deps.workspace == tmp_path
    assert deps.requester is not None


def test_build_memory_runtime_exposes_default_memory_engine(
    monkeypatch,
    tmp_path: Path,
):
    import bootstrap.memory as memory_module

    monkeypatch.setattr(
        memory_module,
        "register_memory_meta_tools",
        lambda *args, **kwargs: None,
    )

    runtime = build_memory_runtime(
        config=Config(
            provider="test",
            model="gpt-test",
            api_key="k",
            memory=MemoryConfig(enabled=True),
        ),
        workspace=tmp_path,
        tools=ToolRegistry(),
        provider=cast(Any, SimpleNamespace()),
        light_provider=None,
        http_resources=cast(Any, SimpleNamespace(external_default=SimpleNamespace())),
    )

    assert runtime.engine is not None
    assert runtime.engine.describe().name == "default"
    assert (
        MemoryCapability.SEMANTICS_RICH_MEMORY in runtime.engine.describe().capabilities
    )
